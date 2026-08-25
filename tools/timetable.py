#!/usr/bin/env python3
"""1~9호선 열차 시간표를 서울 열린데이터광장에서 받아 data/ 로 굽는다.

network.json 이 먼저 있어야 한다 (tools/build.py). 역을 좌표로 이어 붙이기 때문이다.

인증키는 레포에 두지 않는다. 환경변수 SEOUL_API_KEY 를 먼저 보고, 없으면 macOS
키체인에서 `data-seoul-key-normal` 를 꺼낸다. 발급은 data.seoul.go.kr 인증키 신청.

원격 응답은 .cache/timetable_raw.json 에 그대로 저장하고 재실행 때 그걸 쓴다
(--refresh 로만 다시 받는다). 654개 역 × 요일 3 × 방향 2 라 처음 한 번은 오래 걸린다.
같은 캐시로 몇 번을 돌려도 결과 파일은 바이트까지 같다.

굽는 것:

data/timetable-1.json  평일
data/timetable-2.json  토요일
data/timetable-3.json  휴일
    한 편의 열차가 한 원소다. t 기준 오름차순.
      l  노선 id ("1"~"9")   d  1 상행 / 2 하행
      t  첫 정차 시각(초, 자정 기준. 25:10 같은 값이 그대로 90600 으로 온다)
      s  정차 역 번호 배열 — network.json stations[].i
      o  s 와 같은 길이, t 로부터의 경과 초

data/.station_map.json
    우리 역 번호 ↔ 서울시 역 코드. 이름이 아니라 좌표로 붙인다 — 시청·중구청처럼
    노선마다 다른 동명이역이 있어 이름으로는 틀린 역에 붙는다.

1~9호선만 있다. 경의중앙·수인분당·인천 1·2호선 등 나머지는 같은 API 가 INFO-200 을
돌려준다. 운영사가 달라 출처를 따로 찾아야 한다 (docs/NEXT_STEP.md).
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache")
DATA = os.path.join(ROOT, "data")

HOST = "http://openapi.seoul.go.kr:8088"

# LINE_NUM 이 이 표에 없으면 우리 노선이 아니다.
LINES = {f"{n:02d}호선": str(n) for n in range(1, 10)}

# 좌표 매칭 허용 반경. 782개 코드 중 가장 먼 것이 야목 525m 다. 여기서 걸러지는
# 5개 역(청산·도라산·인천공항2터미널·삼양·서해구청)은 서울시 관할 밖이라 API 에 없다.
MATCH_M = 600


def key():
    k = os.environ.get("SEOUL_API_KEY")
    if k:
        return k.strip()
    r = subprocess.run(
        ["security", "find-generic-password", "-s", "data-seoul-key-normal", "-w"],
        capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    sys.exit("인증키가 없다. SEOUL_API_KEY 를 넣거나 키체인에 data-seoul-key-normal 을 두어라.")


def get(url, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if attempt == tries - 1:
                return {"_err": str(e)}
            time.sleep(2 * (attempt + 1))


def paged(k, service, *args):
    """열린데이터광장은 1000건 단위로만 준다. list_total_count 까지 이어 받는다."""
    out, start = [], 1
    while True:
        u = f"{HOST}/{k}/json/{service}/{start}/{start + 999}/" + "".join(f"{a}/" for a in args)
        body = get(u).get(service)
        if not body:
            break
        rows = body.get("row") or []
        out += rows
        start += 1000
        if not rows or start > (body.get("list_total_count") or 0):
            break
    return out


def match_stations(k, stations):
    """역 코드를 좌표로 붙인다. 이름으로 붙이면 동명이역에서 틀린다.

    **한 역에 코드가 여러 개다.** 환승역은 노선마다 코드가 따로 있어서(서울역 6개,
    왕십리 5개) 역마다 하나만 잡으면 나머지 노선 열차의 그 정차가 통째로 빠진다.
    그래서 역이 아니라 코드를 돌면서 가장 가까운 역에 붙인다.
    """
    master = paged(k, "subwayStationMaster")
    pairs, far = [], []
    for r in master:
        try:
            la, lo = float(r["LAT"]), float(r["LOT"])
        except (KeyError, TypeError, ValueError):
            continue
        d, s = min((math.hypot((s["lon"] - lo) * 88.8, (s["lat"] - la) * 111.0) * 1000, s)
                   for s in stations)
        if d <= MATCH_M:
            pairs.append({"i": s["i"], "n": s["n"], "cd": r["BLDN_ID"], "m": round(d)})
        else:
            far.append(r.get("STATN_NM") or r["BLDN_ID"])
    if far:
        print(f"  우리 노선망에 없는 코드 {len(far)}개: {', '.join(far)}", file=sys.stderr)
    return pairs


def fetch_raw(k, codes, have=None):
    """이미 받아 둔 코드는 건너뛴다. 역이 늘어도 늘어난 것만 부른다."""
    out = dict(have or {})
    todo = [c for c in codes if c not in out]
    print(f"  받을 코드 {len(todo)} / 전체 {len(codes)}", file=sys.stderr)
    for n, cd in enumerate(todo, 1):
        rows = []
        for week in (1, 2, 3):        # 평일·토·휴일
            for inout in (1, 2):      # 상행·하행
                rows += paged(k, "SearchSTNTimeTableByIDService", cd, week, inout)
        out[cd] = rows
        if n % 25 == 0:
            print(f"  {n}/{len(todo)}역 · 누적 {sum(len(v) for v in out.values())}행",
                  file=sys.stderr)
    return out


def secs(t):
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


def bake(raw, smap):
    """열차번호가 역과 역을 잇는 열쇠다. 한 편의 정차 순서와 시각이 그대로 이어진다.

    시각은 ARRIVETIME 만 쓴다. 출발역 행은 그게 00:00:00 이라 그 한 정차만 빠지는데,
    LEFTTIME 을 섞으면 같은 역이 도착·출발 두 번 들어와 정차 수가 어긋난다.
    """
    trains = defaultdict(list)
    for cd, rows in raw.items():
        i = smap.get(cd)
        if i is None:
            continue
        for r in rows:
            if r["LINE_NUM"] not in LINES:
                continue
            a = r.get("ARRIVETIME") or ""
            if not a or a == "00:00:00":
                continue
            trains[(r["WEEK_TAG"], r["TRAIN_NO"], LINES[r["LINE_NUM"]], r["INOUT_TAG"])
                   ].append((secs(a), i))

    out = {"1": [], "2": [], "3": []}
    dropped = 0
    for (week, _no, line, inout), stops in trains.items():
        stops = sorted(set(stops))
        if len(stops) < 2:            # 한 역만 서는 건 열차로 그릴 수 없다
            dropped += 1
            continue
        t0 = stops[0][0]
        out[week].append({
            "l": line,
            "d": int(inout),
            "t": t0,
            "s": [i for _, i in stops],
            "o": [s - t0 for s, _ in stops],
        })
    for week in out:
        out[week].sort(key=lambda x: x["t"])
    return out, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="캐시를 무시하고 다시 받는다")
    args = ap.parse_args()

    net_path = os.path.join(DATA, "network.json")
    if not os.path.exists(net_path):
        sys.exit("data/network.json 이 없다. tools/build.py 를 먼저 돌려라.")
    with open(net_path, encoding="utf-8") as f:
        stations = json.load(f)["stations"]

    map_path = os.path.join(DATA, ".station_map.json")
    raw_path = os.path.join(CACHE, "timetable_raw.json")

    k = None
    if args.refresh or not os.path.exists(map_path):
        k = key()
        pairs = match_stations(k, stations)
        os.makedirs(DATA, exist_ok=True)
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(pairs, f, ensure_ascii=False, separators=(",", ":"))
    else:
        with open(map_path, encoding="utf-8") as f:
            pairs = json.load(f)
    smap = {p["cd"]: p["i"] for p in pairs}
    print(f"코드 {len(smap)} → 역 {len(set(smap.values()))}", file=sys.stderr)

    raw = {}
    if os.path.exists(raw_path) and not args.refresh:
        with open(raw_path, encoding="utf-8") as f:
            raw = json.load(f)
    if args.refresh or set(smap) - set(raw):
        raw = fetch_raw(k or key(), sorted(smap), None if args.refresh else raw)
        os.makedirs(CACHE, exist_ok=True)
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
    else:
        print("  cache hit  timetable_raw.json", file=sys.stderr)

    out, dropped = bake(raw, smap)
    for week in ("1", "2", "3"):
        p = os.path.join(DATA, f"timetable-{week}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out[week], f, ensure_ascii=False, separators=(",", ":"))
    total = sum(len(v) for v in out.values())
    print(f"열차 {total}편 (평일 {len(out['1'])} 토 {len(out['2'])} 휴일 {len(out['3'])})"
          f" · 1정차뿐이라 버림 {dropped}", file=sys.stderr)


if __name__ == "__main__":
    main()
