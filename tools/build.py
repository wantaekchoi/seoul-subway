#!/usr/bin/env python3
"""수도권 전철 노선망을 Overpass(형상)와 Wikidata(개통일)에서 받아 data/ 로 굽는다.

원격 응답은 .cache/ 에 그대로 저장하고 재실행 때 그걸 쓴다. Overpass 는 공용 서버라
rate limit 이 있으니 캐시가 있으면 다시 부르지 않는다 (--refresh 로만 강제).
같은 캐시로 몇 번을 돌려도 결과 파일은 바이트까지 같다.

굽는 것 두 개:

data/network.json
    {generated, source, span, lines[], stations[], segments[]}
    segments 는 역-역 구간이고 열차를 얹을 단위다.
      l  노선 id      a, b  양끝 역 번호 (a < b)
      t  개통 시점    m  구간 길이(미터)
      g  실제 선로 폴리라인 [[lat, lon], ...] — a 에서 b 로 가는 순서.
         **없으면 그 구간은 선로 형상을 못 찾은 것이다.** 화면은 직선으로 그리면 된다.
         (추정해서 채우지 않는다. m 은 그때 직선거리다.)
      d  1 이면 노선의 기준 진행 방향이 a -> b, 0 이면 b -> a.
         기준은 그 노선에서 정차역이 가장 많은 relation 의 진행 순서다. 한 노선 안에서는
         일관되지만 공식 상행/하행과 같다는 보장은 없다 (OSM 에 그 표시가 없다).

    basemap 은 배경 지도 파일과 그 출처다. 표기 의무가 있어 같이 남긴다.

data/basemap.topo.json
    배경 지도. 표준 TopoJSON 이고 objects 는 둘이다.
      sigungu  시군구 경계 폴리곤 (SGIS 2018, 공공누리 1유형). 노선망 bbox 에 걸치는 것만.
      water    물길 폴리곤 (OSM, ODbL). 첫 고리가 바깥, 나머지는 섬이다.
    서해는 폴리곤이 없다 — 바탕을 물색으로 깔고 sigungu 를 육지색으로 덮으면 바다가 남는다.

python3 tools/build.py --selftest 로 이어붙이기·자르기 로직만 따로 확인한다.
"""
import gzip
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache")
DATA = os.path.join(ROOT, "data")

# 수도권 bbox (남: 평택, 북: 연천, 서: 인천, 동: 춘천)
BBOX = "36.8,126.3,38.2,127.9"

# 물길은 화면 밖으로 흘러 나가야 강처럼 보인다. 노선망 bbox 보다 넉넉히 잡는다.
WATER_BBOX = "36.6,126.2,38.3,127.9"

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]

# route=light_rail / route=train 에는 KTX·화물·북한 노선까지 섞여 들어온다.
# 수도권 전철 운임구역에 드는 것만 ref 로 추린다. (AREX 직통열차는 중간역을 안 서서
# 서울역~인천공항이 한 줄로 이어져 버리므로 같은 선로의 일반열차 쪽만 쓴다.)
EXTRA_REFS = {
    "용인", "김포 골드라인", "I2", "Silim", "U", "W",       # light_rail
    "서해", "경춘", "공항철도", "경의·중앙", "수인·분당", "GTX-A",  # train
}

# 노선 dot 을 겹쳐 그릴 때 OSM colour 가 비는 노선의 대체색
FALLBACK_COLOR = "#888888"

UA = "seoul-subway-timeline/0.1 (static site data build)"

# ------------------------------------------------------------------ 원격


def _get(url, data=None, timeout=300):
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Encoding", "gzip")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8")


def cached(name, fetch, refresh=False):
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and not refresh:
        print(f"  cache hit  {name}", file=sys.stderr)
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    print(f"  fetching   {name}", file=sys.stderr)
    obj = fetch()
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return obj


def overpass(query):
    """미러를 돌며 재시도. 공용 서버라 busy 응답이 잦다."""
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(3):
        for url in OVERPASS_MIRRORS:
            try:
                txt = _get(url, data=body)
                if not txt.lstrip().startswith("{"):
                    raise RuntimeError(re.sub(r"\s+", " ", txt)[:200])
                return json.loads(txt)
            except Exception as e:  # noqa: BLE001 - 미러마다 실패 사유가 제각각
                last = f"{url}: {e}"
                print(f"  ! {last}", file=sys.stderr)
        time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"overpass 전 미러 실패: {last}")


def wikidata(query):
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
        {"query": query, "format": "json"}
    )
    return json.loads(_get(url, timeout=180))


def routes_query(route_type):
    return f"""
[out:json][timeout:300];
rel["route"="{route_type}"]({BBOX})->.r;
(.r; node(r.r););
out body;
"""


def ways_query(way_ids):
    """관계가 참조하는 선로 way 만 id 로 집어 받는다. bbox 로 받으면 KTX·화물 선로까지 딸려온다."""
    return "[out:json][timeout:300];\nway(id:%s);\nout geom;\n" % ",".join(
        str(i) for i in way_ids
    )


def water_query():
    """물길. 이 지역에서 실제로 쓰이는 태그를 세어 보고 골랐다.

    쓰이는 것은 natural=water 다. waterway=riverbank 는 폐기된 태그라 수도권에 0건이었다.
    water=river 만 걸면 한강은 잡히지만 임진강 일대는 물 종류 없이 natural=water 로만
    그려져 있어 통째로 빠진다. 그래서 종류를 걸지 않고 큰 것만 받는다 — 둘레 1km 미만인
    웅덩이는 어차피 화면에서 점 하나다. 멀티폴리곤은 relation 이라 길이를 못 재니 다 받고
    면적으로 거른다.

    서해 수면은 OSM 에 폴리곤이 없다 (natural=coastline 으로만 그린다). 시군구 경계가
    해안선을 따라가므로 바탕을 물색으로 깔고 육지를 덮으면 바다가 남는다.
    """
    return f"""
[out:json][timeout:300];
(
  way["natural"="water"](if:length()>1000)({WATER_BBOX});
  rel["natural"="water"]({WATER_BBOX});
);
out geom;
"""


WIKIDATA_STATIONS = """
SELECT ?s ?sLabel ?coord ?opened WHERE {
  ?s wdt:P31/wdt:P279* wd:Q55488 .
  ?s wdt:P17 wd:Q884 .
  OPTIONAL { ?s wdt:P625 ?coord }
  OPTIONAL { ?s wdt:P1619 ?opened }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ko,en". }
}
"""

# ------------------------------------------------------------------ 변환

PAREN = re.compile(r"[(（].*?[)）]")


def norm(name):
    """'서울역', '숭실대입구(살피재)' 처럼 표기가 갈리는 역 이름을 맞대볼 키로 줄인다."""
    s = PAREN.sub("", name or "").strip()
    s = re.sub(r"\s+", "", s)
    if len(s) > 1 and s.endswith("역"):
        s = s[:-1]
    return s


def haversine(a_lat, a_lon, b_lat, b_lon):
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


MONTH_START = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def decimal_year(iso):
    """'1899-09-18T00:00:00Z' -> 1899.71. 슬라이더를 연 단위보다 부드럽게 굴리려고 쓴다."""
    y, m, d = int(iso[0:4]), int(iso[5:7]), int(iso[8:10])
    return round(y + (MONTH_START[m - 1] + d) / 366.0, 3)


def collect_lines(datasets):
    """방향·급행·계통별로 쪼개진 relation 들을 ref 하나로 합친다."""
    rels_by_ref = defaultdict(list)
    nodes = {}
    for osm in datasets:
        for e in osm["elements"]:
            if e["type"] == "node":
                nodes[e["id"]] = e
        for e in osm["elements"]:
            if e["type"] != "relation":
                continue
            ref = (e.get("tags") or {}).get("ref")
            if not ref:
                continue
            rels_by_ref[ref].append(e)
    return rels_by_ref, nodes


def cluster_stations(rels_by_ref, nodes):
    """같은 역의 방향별·노선별 stop 노드를 하나로 묶는다.

    ponytail: 이름이 같고 500m 안이면 같은 역으로 본다. 신촌(2호선)과 신촌(경의중앙)처럼
    이름이 같고 실제로 다른 역은 갈라지고, 서울역처럼 승강장이 넓게 퍼진 역은 쪼개질 수 있다.
    둘 다 점 위치만 어긋나므로 지금은 감수한다. 환승 관계를 그리게 되면 그때 손본다.
    """
    used = set()
    for rels in rels_by_ref.values():
        for r in rels:
            for m in r["members"]:
                if m["type"] == "node" and m["role"].startswith("stop"):
                    used.add(m["ref"])
    by_name = defaultdict(list)
    for nid in used:
        n = nodes.get(nid)
        if not n:
            continue
        name = (n.get("tags") or {}).get("name")
        if not name:
            continue
        by_name[norm(name)].append(n)

    stations = []
    node_to_station = {}
    for key, group in by_name.items():
        clusters = []  # [[node, ...], ...]
        for n in group:
            for c in clusters:
                if haversine(n["lat"], n["lon"], c[0]["lat"], c[0]["lon"]) < 500:
                    c.append(n)
                    break
            else:
                clusters.append([n])
        for c in clusters:
            sid = len(stations)
            display = Counter((n["tags"].get("name") or "") for n in c).most_common(1)[0][0]
            stations.append(
                {
                    "i": sid,
                    "n": display,
                    "k": key,
                    "lat": round(sum(n["lat"] for n in c) / len(c), 6),
                    "lon": round(sum(n["lon"] for n in c) / len(c), 6),
                }
            )
            for n in c:
                node_to_station[n["id"]] = sid
    return stations, node_to_station


# 실형상 폴리라인을 화면에서 얼마나 매끈하게 볼 것인가. 12m 면 곡선이 살고 점은 절반 아래로 준다.
GEOM_TOL_M = 12


def stitch(rel, ways):
    """relation 의 선로 way 를 이어 붙여 (노드 id, lat, lon) 열로 만든다.

    way 는 relation 안에서 방향이 제각각이라 앞 조각의 끝과 맞는 쪽으로 돌려 붙인다.
    첫 조각은 아직 방향을 모르니 두 번째 조각이 붙을 때 같이 뒤집어 본다.
    끝이 안 맞으면 선로가 끊긴 것이므로 거기서 열을 자른다 (이어 붙이지 않는다).
    """
    runs, cur, pieces = [], [], 0
    for m in rel["members"]:
        if m["type"] != "way":
            continue
        w = ways.get(m["ref"])
        if not w:
            continue
        pts = [(nid, g["lat"], g["lon"]) for nid, g in zip(w["nodes"], w["geometry"])]
        if len(pts) < 2:
            continue
        if not cur:
            cur, pieces = pts, 1
            continue
        joined = False
        for base in ([cur] if pieces > 1 else [cur, cur[::-1]]):
            if pts[0][0] == base[-1][0]:
                cur, joined = base + pts[1:], True
            elif pts[-1][0] == base[-1][0]:
                cur, joined = base + pts[-2::-1], True
            if joined:
                break
        if joined:
            pieces += 1
        else:
            runs.append(cur)
            cur, pieces = pts, 1
    if cur:
        runs.append(cur)
    return runs


def place_stops(runs, stop_nodes):
    """정차 노드가 이어 붙인 선로의 어디에 놓이는지 (열 번호, 자리)로 찾는다.

    2호선처럼 같은 자리를 두 번 지나는 노선이 있어 앞 정차역보다 뒤에 오는 자리를 먼저 고른다.
    """
    occ = defaultdict(list)
    for ri, run in enumerate(runs):
        for i, (nid, _, _) in enumerate(run):
            occ[nid].append((ri, i))
    out, prev = [], None
    for nid in stop_nodes:
        cands = occ.get(nid)
        if not cands:
            out.append(None)
            continue
        pick = None
        if prev:
            later = [c for c in cands if c[0] == prev[0] and c[1] > prev[1]]
            if later:
                pick = min(later, key=lambda c: c[1])
        out.append(pick or cands[0])
        prev = out[-1]
    return out


def polyline_m(pts):
    return sum(haversine(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:]))


def slice_geom(runs, pa, pb, straight):
    """정차역 두 자리 사이의 선로 조각. 없거나 미덥지 않으면 None (직선으로 남긴다)."""
    if not pa or not pb or pa[0] != pb[0] or pa[1] == pb[1]:
        return None
    i, j = pa[1], pb[1]
    run = runs[pa[0]]
    cut = run[i:j + 1] if i < j else run[j:i + 1][::-1]
    pts = [(la, lo) for _, la, lo in cut]
    # 순환선을 반대로 한 바퀴 돌아 잘리는 등 엉뚱하게 잘린 조각을 걸러낸다.
    if polyline_m(pts) > straight * 3 + 1000:
        return None
    return pts


def build_segments(rels_by_ref, node_to_station, ways, coords):
    """relation 의 정차역 순서를 이웃 쌍으로 끊는다. 역-역 구간이 열차를 얹을 단위다.

    구간마다 실제 선로 형상(g)·길이(m)·진행 방향(d)을 같이 낸다. 형상을 못 찾은 구간은
    g 가 없고, 그때 길이는 직선거리다.
    """
    lines, segments, seen = [], [], set()
    for ref, rels in sorted(rels_by_ref.items()):
        colors = Counter(r["tags"]["colour"] for r in rels if r["tags"].get("colour"))
        names = Counter(r["tags"]["name"].split(":")[0].strip() for r in rels if r["tags"].get("name"))
        line = {
            "id": ref,
            "name": names.most_common(1)[0][0] if names else ref,
            "color": colors.most_common(1)[0][0] if colors else FALLBACK_COLOR,
        }
        rels = sorted(rels, key=lambda r: r["id"])
        stoplist = {
            r["id"]: [
                (node_to_station[m["ref"]], m["ref"])
                for m in r["members"]
                if m["type"] == "node"
                and m["role"].startswith("stop")
                and m["ref"] in node_to_station
            ]
            for r in rels
        }
        # 상·하행 relation 이 반반씩 섞여 있어 그냥 세면 방향이 동전 던지기가 된다.
        # 정차역이 가장 많은 relation 을 기준으로 두고 나머지가 뒤집힌 쪽인지 판정해 맞춘다.
        base = max(rels, key=lambda r: (len(stoplist[r["id"]]), -r["id"]))
        pos = {}
        for i, (st, _) in enumerate(stoplist[base["id"]]):
            pos.setdefault(st, i)
        count = 0
        for r in rels:
            sl = stoplist[r["id"]]
            score = sum(
                1 if pos[x] < pos[y] else -1
                for (x, _), (y, _) in zip(sl, sl[1:])
                if x in pos and y in pos and pos[x] != pos[y]
            )
            flip = score < 0
            runs = stitch(r, ways)
            places = place_stops(runs, [nid for _, nid in sl])
            for k in range(len(sl) - 1):
                a, b = sl[k][0], sl[k + 1][0]
                if a == b:
                    continue
                key = (ref, min(a, b), max(a, b))
                if key in seen:
                    continue
                seen.add(key)
                (alat, alon), (blat, blon) = coords[key[1]], coords[key[2]]
                straight = haversine(alat, alon, blat, blon)
                geom = slice_geom(runs, places[k], places[k + 1], straight)
                sg = {"l": ref, "a": key[1], "b": key[2]}
                if geom:
                    if a != key[1]:
                        geom = geom[::-1]
                    sg["m"] = round(polyline_m(geom))
                    sg["g"] = thin(geom)
                else:
                    sg["m"] = round(straight)
                # d: 기준 방향(상행)이 a -> b 면 1, b -> a 면 0.
                ahead = (b, a) if flip else (a, b)
                sg["d"] = 1 if ahead == (key[1], key[2]) else 0
                segments.append(sg)
                count += 1
        if count:
            lines.append(line)
    return lines, segments


def thin(pts):
    """폴리라인을 화면에 필요한 만큼만 남긴다. 소수점 5자리는 약 1m 다."""
    kx, ky = 88400.0, 111200.0  # 위도 37.5도 부근 1도의 미터
    flat = [(lo * kx, la * ky) for la, lo in pts]
    out = []
    for i in simplify(flat, GEOM_TOL_M):
        p = [round(pts[i][0], 5), round(pts[i][1], 5)]
        if not out or p != out[-1]:
            out.append(p)
    return out


def attach_opening_dates(stations, binds):
    """Wikidata 역을 이름 + 근접으로 붙인다. 없으면 비워 둔다 (추정 금지)."""
    wd = {}
    for b in binds:
        qid = b["s"]["value"]
        rec = wd.setdefault(qid, {"label": None, "lat": None, "lon": None, "opened": None})
        rec["label"] = b.get("sLabel", {}).get("value") or rec["label"]
        if "coord" in b and rec["lat"] is None:
            m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
            if m:
                rec["lon"], rec["lat"] = float(m.group(1)), float(m.group(2))
        if "opened" in b:
            v = b["opened"]["value"]
            # 재건축 등으로 P1619 가 여럿인 역이 있다. 가장 이른 것이 개통일이다.
            if rec["opened"] is None or v < rec["opened"]:
                rec["opened"] = v

    by_key = defaultdict(list)
    for rec in wd.values():
        if rec["label"]:
            by_key[norm(rec["label"])].append(rec)

    matched = 0
    for st in stations:
        best, best_d = None, 5000.0
        for rec in by_key.get(st["k"], []):
            if rec["lat"] is None:
                continue
            d = haversine(st["lat"], st["lon"], rec["lat"], rec["lon"])
            if d < best_d:
                best, best_d = rec, d
        if best and best["opened"]:
            st["o"] = best["opened"][:10]
            st["t"] = decimal_year(best["opened"])
            matched += 1
    return matched


def line_floor(lines, segments, stations):
    """노선은 제 노선에만 있는 역보다 먼저 생길 수 없다.

    사이 역이 끼어든 옛 구간을 건너뛰어 이어 붙이는 쪽은 버렸다. 1974년 화면에 4호선이
    서울역에서 창동까지 곧게 그어졌다 — 두 역은 그때 경부선·경원선 역으로 있었지만
    4호선은 1985년에 생겼다. 거리로 자르는 방법도 안 된다. 참인 경인선 부천–영등포가
    9km, 거짓인 4호선 서울역–창동이 11km 라 상수 하나로 안 갈린다.

    9호선 여의도-당산처럼 옛 환승역을 이어받은 구간은 양끝 역이 다 오래됐다는 이유로
    노선이 생기기 수십 년 전에 열린 것으로 잡힌다. 그 노선에만 있는 역 중 가장 이른
    개통일을 하한으로 눌러 준다. 개통일을 지어내는 게 아니라 데이터 안에서 끌어낸 하한이라
    실제 개통일보다 이를 수는 있어도 늦지는 않는다.
    """
    lines_of = defaultdict(set)
    for g in segments:
        lines_of[g["a"]].add(g["l"])
        lines_of[g["b"]].add(g["l"])
    tmap = {s["i"]: s.get("t") for s in stations}
    floor = {}
    for line in lines:
        own = [
            tmap[i] for i, ls in lines_of.items()
            if ls == {line["id"]} and tmap.get(i) is not None
        ]
        if own:
            floor[line["id"]] = min(own)
    return floor


# ------------------------------------------------------------------ 배경 지도

# 시군구 경계 원본. SGIS(통계청) 2018 기준 250개, WGS84, 공공누리 1유형.
SIGUNGU = os.path.join(ROOT, "assets", "sigungu.topo.json")
BASEMAP_SOURCE = (
    "시군구 경계: SGIS(통계청) 2018년 기준 행정구역, 공공누리 제1유형"
    " / 물길: OpenStreetMap 기여자, ODbL"
)

# 배경 지도라 정밀도보다 용량이 중요하다. 화면 전체가 130km 쯤이니 150m 는 1~2px 이다.
BOUNDARY_TOL_M = 200
WATER_TOL_M = 60
# 이보다 작은 물은 화면에서 점 하나다. 용량만 먹으므로 버린다.
MIN_WATER_M2 = 300000


def simplify(pts, tol):
    """Douglas-Peucker. 남길 점의 인덱스를 준다. 양끝은 남으므로 닫힌 고리는 닫힌 채다."""
    if len(pts) < 3:
        return list(range(len(pts)))
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = pts[a]
        dx, dy = pts[b][0] - ax, pts[b][1] - ay
        dd = dx * dx + dy * dy
        far, at = -1.0, a
        for i in range(a + 1, b):
            px, py = pts[i]
            if dd == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / dd))
                d2 = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d2 > far:
                far, at = d2, i
        if far > tol * tol:
            keep[at] = True
            stack.append((a, at))
            stack.append((at, b))
    return [i for i, k in enumerate(keep) if k]


def arc_indices(a, out):
    if isinstance(a, int):
        out.append(a if a >= 0 else ~a)
    else:
        for x in a:
            arc_indices(x, out)


def clip_sigungu(bbox, margin=0.1):
    """전국 topojson 에서 노선망 bbox + 여백에 걸치는 시군구만 남긴다.

    경계선은 arc 를 이웃 시군구가 공유하므로 topojson 인 채로 자르고 단순화한다.
    폴리곤마다 따로 풀어 단순화하면 공유 경계가 서로 어긋나 틈이 벌어진다.
    """
    topo = json.load(open(SIGUNGU, encoding="utf-8"))
    obj = next(iter(topo["objects"].values()))
    sc, tr = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for a in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in a:
            x += dx
            y += dy
            pts.append((x, y))
        arcs.append(pts)

    lo_x, lo_y = bbox[0] - margin, bbox[1] - margin
    hi_x, hi_y = bbox[2] + margin, bbox[3] + margin

    def inside(p):
        return lo_x <= p[0] * sc[0] + tr[0] <= hi_x and lo_y <= p[1] * sc[1] + tr[1] <= hi_y

    keep = []
    for g in obj["geometries"]:
        idx = []
        arc_indices(g["arcs"], idx)
        if any(inside(p) for i in idx for p in arcs[i]):
            keep.append(g)

    used = []
    for g in keep:
        arc_indices(g["arcs"], used)
    used = sorted(set(used))
    tol = BOUNDARY_TOL_M / unit_m(sc)
    remap, out_arcs = {}, []
    for i in used:
        remap[i] = len(out_arcs)
        out_arcs.append(delta([arcs[i][k] for k in simplify(arcs[i], tol)]))

    def renum(a):
        if isinstance(a, int):
            return remap[a] if a >= 0 else ~remap[~a]
        return [renum(x) for x in a]

    geoms = [
        {
            "type": g["type"],
            "arcs": renum(g["arcs"]),
            "properties": {
                "name": g["properties"]["name"],
                "code": g["properties"]["code"],
            },
        }
        for g in keep
    ]
    return topo["transform"], out_arcs, geoms


def unit_m(scale):
    """양자화 한 칸이 몇 미터인가. 위도 37.5도 기준 (경도 6.4m, 위도 6.1m 라 평균낸다)."""
    return (scale[0] * 88400 + scale[1] * 111200) / 2


def delta(pts):
    out, px, py = [], 0, 0
    for x, y in pts:
        out.append([x - px, y - py])
        px, py = x, y
    return out


def rings_from_lines(lines):
    """끝점이 맞는 선들을 이어 닫힌 고리로 만든다. 못 닫으면 버린다 (추정해서 잇지 않는다).

    ponytail: 매번 남은 조각을 처음부터 훑는 O(n^2). 멀티폴리곤 하나에 way 수백 개까지라
    문제 없다. 전국 규모로 키우면 끝점 해시로 바꿀 것.
    """
    pool = [list(l) for l in lines if len(l) >= 2]
    rings = []
    while pool:
        cur = pool.pop()
        while cur[0] != cur[-1]:
            for i, p in enumerate(pool):
                if p[0] == cur[-1]:
                    cur = cur + p[1:]
                elif p[-1] == cur[-1]:
                    cur = cur + p[-2::-1]
                elif p[-1] == cur[0]:
                    cur = p[:-1] + cur
                elif p[0] == cur[0]:
                    cur = p[:0:-1] + cur
                else:
                    continue
                pool.pop(i)
                break
            else:
                cur = None
                break
        if cur:
            rings.append(cur)
    return rings


def ring_area(ring):
    lat0 = sum(p[1] for p in ring) / len(ring)
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        s += (x1 * kx) * (y2 * ky) - (x2 * kx) * (y1 * ky)
    return abs(s) / 2


def water_polygons(osm, bbox, margin=0.08):
    """natural=water + water=river 를 폴리곤(바깥 고리 + 섬 고리)으로 모은다.

    화면 밖으로 흘러 나가라고 넓게 받았으므로 여기서 화면 범위로 다시 자른다.
    """
    polys = []
    for e in osm["elements"]:
        name = (e.get("tags") or {}).get("name")
        if e["type"] == "way":
            pts = [(round(p["lon"], 7), round(p["lat"], 7)) for p in e.get("geometry", [])]
            outer, inner = rings_from_lines([pts]), []
        elif e["type"] == "relation":
            def lines(role):
                return [
                    [(round(p["lon"], 7), round(p["lat"], 7)) for p in m.get("geometry", [])]
                    for m in e["members"]
                    if m["type"] == "way" and (m["role"] or "outer") == role
                ]
            outer, inner = rings_from_lines(lines("outer")), rings_from_lines(lines("inner"))
        else:
            continue
        for r in outer:
            if ring_area(r) < MIN_WATER_M2:
                continue
            if (min(p[0] for p in r) > bbox[2] + margin
                    or max(p[0] for p in r) < bbox[0] - margin
                    or min(p[1] for p in r) > bbox[3] + margin
                    or max(p[1] for p in r) < bbox[1] - margin):
                continue
            holes = [h for h in inner if ring_area(h) >= MIN_WATER_M2 and inside_ring(h[0], r)]
            polys.append((name, r, holes))
    polys.sort(key=lambda p: (-ring_area(p[1]), p[0] or ""))
    return polys


def inside_ring(pt, ring):
    x, y = pt
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) / (y2 - y1) * (x2 - x1):
            hit = not hit
    return hit


def build_basemap(bbox, water_osm, path):
    transform, arcs, geoms = clip_sigungu(bbox)
    sc, tr = transform["scale"], transform["translate"]
    tol = WATER_TOL_M / unit_m(sc)
    wgeoms = []
    for name, outer, holes in water_polygons(water_osm, bbox):
        rings = []
        for r in [outer] + holes:
            q = [
                (int(round((x - tr[0]) / sc[0])), int(round((y - tr[1]) / sc[1])))
                for x, y in r
            ]
            q = [q[k] for k in simplify(q, tol)]
            if len(q) < 4:
                continue
            if q[0] != q[-1]:
                q.append(q[0])
            rings.append([len(arcs)])
            arcs.append(delta(q))
        if rings:
            g = {"type": "Polygon", "arcs": rings}
            if name:
                g["properties"] = {"name": name}
            wgeoms.append(g)
    out = {
        "type": "Topology",
        "source": BASEMAP_SOURCE,
        "bbox": [round(v, 4) for v in bbox],
        "transform": transform,
        "objects": {
            "sigungu": {"type": "GeometryCollection", "geometries": geoms},
            "water": {"type": "GeometryCollection", "geometries": wgeoms},
        },
        "arcs": arcs,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return len(geoms), len(wgeoms)


def selftest():
    """way 이어붙이기·정차역 찾기·고리 만들기. 여기가 틀리면 선로가 엉뚱하게 그려진다."""
    def w(nid_pts):
        return {
            "nodes": [n for n, _, _ in nid_pts],
            "geometry": [{"lat": la, "lon": lo} for _, la, lo in nid_pts],
        }
    A = [(1, 0.0, 0.0), (2, 0.0, 1.0)]
    B = [(2, 0.0, 1.0), (3, 0.0, 2.0)]
    ways = {10: w(A), 11: w(B[::-1]), 12: w([(9, 5.0, 5.0), (8, 5.0, 6.0)])}
    rel = {"members": [{"type": "way", "ref": r} for r in (10, 11, 12)]}
    runs = stitch(rel, ways)
    # 뒤집힌 way 는 돌려서 붙고, 안 닿는 way 는 새 열로 끊긴다
    assert [[n for n, _, _ in r] for r in runs] == [[1, 2, 3], [9, 8]], runs
    # 첫 way 가 거꾸로 들어와도 두 번째가 붙을 때 같이 뒤집는다
    rev = {"members": [{"type": "way", "ref": r} for r in (10, 11)]}
    assert [n for n, _, _ in stitch(rev, {10: w(A[::-1]), 11: w(B)})[0]] == [1, 2, 3]
    # 같은 노드를 두 번 지나는 순환선: 앞 정차역보다 뒤에 오는 자리를 고른다
    loop = [[(1, 0, 0), (2, 0, 1), (1, 0, 0), (3, 0, 2)]]
    assert place_stops(loop, [1, 1, 3]) == [(0, 0), (0, 2), (0, 3)]
    assert place_stops(loop, [7]) == [None]
    # 한 바퀴 돌아 잘린 조각은 버린다 (직선거리의 3배 + 1km 넘으면)
    run = [(0, 0.0, 0.0), (0, 0.5, 0.0), (0, 0.0, 0.02)]
    assert slice_geom([run], (0, 0), (0, 2), haversine(0, 0, 0, 0.02)) is None
    assert slice_geom([run], (0, 0), (0, 1), haversine(0, 0, 0.5, 0)) is not None
    # 끝점이 맞는 조각들로 고리를 만들고, 못 닫으면 버린다
    sq = [[(0, 0), (1, 0)], [(1, 1), (1, 0)], [(1, 1), (0, 1)], [(0, 1), (0, 0)]]
    assert [len(r) for r in rings_from_lines(sq)] == [5]
    assert rings_from_lines([[(0, 0), (1, 0)], [(5, 5), (6, 6)]]) == []
    assert round(ring_area([(0, 0), (0.01, 0), (0.01, 0.01), (0, 0.01), (0, 0)]) / 1e6) == 1
    # 일직선 위의 점은 지우고 양끝은 남긴다
    assert simplify([(0, 0), (1, 0), (2, 0), (3, 0)], 0.5) == [0, 3]
    assert simplify([(0, 0), (1, 9), (2, 0)], 0.5) == [0, 1, 2]
    print("selftest ok", file=sys.stderr)


def main():
    if "--selftest" in sys.argv:
        return selftest()
    refresh = "--refresh" in sys.argv
    os.makedirs(DATA, exist_ok=True)
    print("== fetch ==", file=sys.stderr)
    datasets = [
        cached("overpass_subway.json", lambda: overpass(routes_query("subway")), refresh),
        cached("overpass_light_rail.json", lambda: overpass(routes_query("light_rail")), refresh),
        cached("overpass_train.json", lambda: overpass(routes_query("train")), refresh),
    ]
    wd = cached("wikidata_stations.json", lambda: wikidata(WIKIDATA_STATIONS), refresh)

    print("== transform ==", file=sys.stderr)
    rels_by_ref, nodes = collect_lines(datasets)
    subway_refs = {
        (e.get("tags") or {}).get("ref")
        for e in datasets[0]["elements"]
        if e["type"] == "relation"
    }
    keep = {r for r in rels_by_ref if r in subway_refs or r in EXTRA_REFS}
    dropped = sorted(set(rels_by_ref) - keep)
    # 문자열 집합을 그대로 돌면 해시 시드에 따라 역 번호가 달라져 매 빌드마다 파일이 바뀐다.
    rels_by_ref = {r: rels_by_ref[r] for r in sorted(keep)}
    print(f"  노선 {len(keep)}개 채택, {len(dropped)}개 제외 ({', '.join(dropped[:6])}...)", file=sys.stderr)

    way_ids = sorted({
        m["ref"] for rels in rels_by_ref.values() for r in rels
        for m in r["members"] if m["type"] == "way"
    })
    ways = {
        w["id"]: w
        for w in cached(
            "overpass_ways.json", lambda: overpass(ways_query(way_ids)), refresh
        )["elements"]
        if w["type"] == "way" and w.get("geometry")
    }
    water = cached("overpass_water.json", lambda: overpass(water_query()), refresh)
    print(f"  선로 way {len(ways)} / 물길 요소 {len(water['elements'])}", file=sys.stderr)

    stations, node_to_station = cluster_stations(rels_by_ref, nodes)
    coords = {st["i"]: (st["lat"], st["lon"]) for st in stations}
    lines, segments = build_segments(rels_by_ref, node_to_station, ways, coords)
    matched = attach_opening_dates(stations, wd["results"]["bindings"])

    for st in stations:
        del st["k"]
        st["lat"] = round(st["lat"], 5)
        st["lon"] = round(st["lon"], 5)

    # 구간은 양끝 역이 다 열려야 열린다. 한쪽이라도 개통일을 모르면 구간도 미상이다.
    tmap = {s["i"]: s.get("t") for s in stations}
    floor = line_floor(lines, segments, stations)
    dated_seg = 0
    for sg in segments:
        ta, tb = tmap.get(sg["a"]), tmap.get(sg["b"])
        if ta is not None and tb is not None:
            sg["t"] = round(max(ta, tb, floor.get(sg["l"], 0)), 3)
            dated_seg += 1
    for line in lines:
        line["from"] = floor.get(line["id"])

    years = sorted(s["t"] for s in stations if s.get("t") is not None)
    # 연표는 오늘까지 이어진다. 마지막 개통 이후로 아무것도 안 열렸다는 것도 정보다.
    today = decimal_year(time.strftime("%Y-%m-%dT00:00:00Z"))
    out = {
        "generated": time.strftime("%Y-%m-%d"),
        "source": "OpenStreetMap (ODbL) / Wikidata (CC0)",
        # 배경 지도는 출처가 달라 파일도 따로다. 화면이 읽는 건 이 파일 하나뿐이라
        # 표기 의무가 있는 출처(공공누리 1유형)를 여기서 찾을 수 있게 남긴다.
        "basemap": {"file": "basemap.topo.json", "source": BASEMAP_SOURCE},
        "span": [math.floor(years[0]), max(years[-1], today)],
        "lines": lines,
        "stations": stations,
        "segments": segments,
    }
    path = os.path.join(DATA, "network.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    bbox = [
        min(s["lon"] for s in stations), min(s["lat"] for s in stations),
        max(s["lon"] for s in stations), max(s["lat"] for s in stations),
    ]
    bpath = os.path.join(DATA, "basemap.topo.json")
    n_sgg, n_water = build_basemap(bbox, water, bpath)

    with_geom = sum(1 for g in segments if "g" in g)
    print(f"  노선 {len(lines)} / 역 {len(stations)} / 구간 {len(segments)}", file=sys.stderr)
    print(f"  실형상 구간 {with_geom} (직선으로 남은 것 {len(segments) - with_geom})", file=sys.stderr)
    print(f"  개통일 있는 역 {matched} (미상 {len(stations) - matched})", file=sys.stderr)
    print(f"  개통일 있는 구간 {dated_seg} (미상 {len(segments) - dated_seg})", file=sys.stderr)
    print("  노선 하한: " + ", ".join(
        f"{l['id']}={int(l['from'])}" for l in lines if l.get("from")), file=sys.stderr)
    print(f"  기간 {out['span'][0]}~{out['span'][1]}", file=sys.stderr)
    print(f"  bbox {[round(v, 3) for v in bbox]} / 시군구 {n_sgg} / 물길 {n_water}", file=sys.stderr)
    for f in (path, bpath):
        print(f"  -> {f} ({os.path.getsize(f) / 1024:.1f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
