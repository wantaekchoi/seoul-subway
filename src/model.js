/* 모델 — 구워 둔 데이터와 그것에서 파생되는 것들. 읽기 전용이고 DOM 을 모른다.
   화면이 무엇을 보여 주든 여기는 안 바뀐다. */

export const DAY = 86400;
export const DWELL = 25;    // 역에 서 있는 시간(초)
export const TURN = 100;    // 종점에서 몸을 돌리는 데 쓰는 시간(초)
export const FRESH = 1.2;   // 갓 열린 역을 강조해 두는 기간(년)
export const TIMED = /^[1-9]$/;   // 시간표가 있는 노선

// 시간표는 자정을 넘겨도 24:45·25:07 처럼 이어 적는다. 화면 시각은 0~86399 라
// 한 번만 빼면 그런 편은 rel 이 음수로 남아 아직 출발도 안 한 열차가 선로 밖 허공에
// 그려진다. 나머지 연산으로 양쪽을 한꺼번에 접는다.
export const relSec = (T, t) => ((T - t) % DAY + DAY) % DAY;

const pad2 = (n) => (n < 10 ? '0' : '') + n;
export const hhmm = (sec) =>
  pad2(Math.floor(sec / 3600) % 24) + ':' + pad2(Math.floor(sec / 60) % 60);

export const grab = (url) => fetch(url).then((r) => {
  if (!r.ok) throw new Error(`${url} ${r.status}`);
  return r.json();
});

export function load() {
  return Promise.all([
    grab('data/network.json'),
    grab('data/basemap.topo.json'),
    // 공휴일 표는 없어도 화면은 뜬다 — 요일로만 고르게 되고 화면이 그렇게 말한다.
    grab('data/holidays.json').catch(() => null),
  ]).then(([net, topo, hol]) => new Model(net, topo, hol));
}

const key = (l, a, b) => l + '|' + a + '|' + b;

// OSM 이름은 접두사가 제각각이다 — 같은 지하철인데 1·3·4호선은 '수도권 전철', 2·5~9호선은
// '서울 지하철' 을 달고 온다. 곁 화면에서는 노선 이름만 남긴다. 원본은 data 에 그대로 있다.
const shortName = (n) => n
  .replace(/^수도권 광역급행철도 (\w)선$/, 'GTX-$1')
  .replace(/^인천국제공항철도 일반열차$/, '공항철도')
  .replace(/^서울 경전철 /, '')
  .replace(/^(수도권 전철|서울 지하철) /, '')
  .replace(/^인천 도시철도 /, '인천 ');

export class Model {
  constructor(net, topo, holidays) {
    this.net = net;
    this.topo = topo;
    this.holidays = holidays;
    this.byId = new Map(net.stations.map((s) => [s.i, s]));
    this.lineOf = new Map(net.lines.map((l) => [l.id, { ...l, name: shortName(l.name) }]));

    // 등장방형도법. 위도 37.4도에서 경도 1도는 위도 1도의 cos 배라 그만큼 좁혀 준다.
    const lats = net.stations.map((s) => s.lat), lons = net.stations.map((s) => s.lon);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLon = Math.min(...lons), maxLon = Math.max(...lons);
    const kx = Math.cos((minLat + maxLat) / 2 * Math.PI / 180);
    const scale = 1000 / Math.max((maxLon - minLon) * kx, maxLat - minLat);
    const PAD = 18;
    this.px = (lon) => (lon - minLon) * kx * scale + PAD;
    this.py = (lat) => (maxLat - lat) * scale + PAD;
    for (const s of net.stations) { s.x = this.px(s.lon); s.y = this.py(s.lat); }
    this.world = {
      w: (maxLon - minLon) * kx * scale + PAD * 2,
      h: (maxLat - minLat) * scale + PAD * 2,
    };

    this.segOf = new Map();      // '노선|a|b' → 구간
    this.adj = new Map();        // 노선 → 역 → 이웃 역들
    this.staOfLine = new Map();  // 노선 → 그 위의 역 번호들
    this.homeLine = new Map();   // 역 → 대표 노선(점 색을 고를 때)
    for (const g of net.segments) {
      this.segOf.set(key(g.l, g.a, g.b), g);
      let m = this.adj.get(g.l);
      if (!m) this.adj.set(g.l, m = new Map());
      for (const [u, v] of [[g.a, g.b], [g.b, g.a]]) {
        let a = m.get(u);
        if (!a) m.set(u, a = []);
        a.push(v);
      }
      let set = this.staOfLine.get(g.l);
      if (!set) this.staOfLine.set(g.l, set = new Set());
      set.add(g.a); set.add(g.b);
      if (!this.homeLine.has(g.a)) this.homeLine.set(g.a, g.l);
      if (!this.homeLine.has(g.b)) this.homeLine.set(g.b, g.l);
    }

    const order = (arr) => arr.map((v, i) => i).filter((i) => arr[i].t != null)
      .sort((a, b) => arr[a].t - arr[b].t);
    this.segAge = order(net.segments);
    this.staAge = order(net.stations);

    this.legs = new Map();
    this.spot = { x: 0, y: 0, a: 0 };
  }

  color(l) { return (this.lineOf.get(l) || {}).color || '#8a94a6'; }
  name(l) { return (this.lineOf.get(l) || {}).name || l; }

  /** 그날이 공휴일이면 이름, 아니면 빈 문자열. 표가 그 해를 안 덮으면 null 이다. */
  holiday(d) {
    const h = this.holidays;
    if (!h) return null;
    const y = d.getFullYear();
    if (y < h.from || y > h.to) return null;
    const p2 = (n) => (n < 10 ? '0' : '') + n;
    return h.dates[`${y}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`] || '';
  }
  seg(l, a, b) { return this.segOf.get(key(l, a, b)) || this.segOf.get(key(l, b, a)); }

  // g 는 a 에서 b 로 가는 실제 선로다. 없는 구간 하나는 직선으로 잇는다.
  pts(g) {
    if (!g._p) {
      g._p = g.g ? g.g.map(([la, lo]) => [this.px(lo), this.py(la)])
                 : [[this.byId.get(g.a).x, this.byId.get(g.a).y],
                    [this.byId.get(g.b).x, this.byId.get(g.b).y]];
      let len = 0;
      for (let i = 1; i < g._p.length; i++) {
        len += Math.hypot(g._p[i][0] - g._p[i - 1][0], g._p[i][1] - g._p[i - 1][1]);
      }
      g._len = len || 1;
    }
    return g._p;
  }

  // 시간표는 정차역만 준다. 통과역이 있으면 같은 노선 안에서 이어지는 길을 찾는다.
  // 정차 쌍의 18% 가 구간 하나로 안 이어진다 — 급행이 지나치는 역과 환승역 코드 차이가
  // 섞여 있다. 두 점을 직선으로 잇는 쪽은 버렸다. 9호선 급행이 한강을 가로질러 날아간다.
  hop(l, u, v) {
    if (this.seg(l, u, v)) return [u, v];
    const m = this.adj.get(l);
    if (!m) return null;
    const prev = new Map([[u, -1]]);
    const q = [u];
    for (let h = 0; h < q.length; h++) {
      for (const y of m.get(q[h]) || []) {
        if (prev.has(y)) continue;
        prev.set(y, q[h]);
        if (y === v) {
          const p = [v];
          while (p[0] !== u) p.unshift(prev.get(p[0]));
          return p;
        }
        q.push(y);
      }
    }
    return null;
  }

  /** u 에서 v 까지의 실제 선로. 누적 거리를 달고 있어 비율로 자리를 찾는다. */
  leg(l, u, v) {
    const k = key(l, u, v);
    if (this.legs.has(k)) return this.legs.get(k);
    const path = this.hop(l, u, v);
    const line = [];
    if (path) {
      for (let i = 0; i < path.length - 1; i++) {
        const g = this.seg(l, path[i], path[i + 1]);
        const p = g.a === path[i] ? this.pts(g) : this.pts(g).slice().reverse();
        for (let j = line.length ? 1 : 0; j < p.length; j++) line.push(p[j]);
      }
    }
    for (let i = line.length - 1; i > 0; i--) {
      if (line[i][0] === line[i - 1][0] && line[i][1] === line[i - 1][1]) line.splice(i, 1);
    }
    let L = null;
    if (line.length > 1) {
      const n = line.length;
      L = { x: new Float64Array(n), y: new Float64Array(n), c: new Float64Array(n), total: 0 };
      for (let i = 0; i < n; i++) {
        L.x[i] = line[i][0]; L.y[i] = line[i][1];
        if (i) L.c[i] = L.c[i - 1] + Math.hypot(L.x[i] - L.x[i - 1], L.y[i] - L.y[i - 1]);
      }
      L.total = L.c[n - 1] || 1;
    }
    this.legs.set(k, L);
    return L;
  }

  /** 선로 위 비율 f 지점의 좌표와 진행 방향. 매 프레임 부르므로 한 자리를 돌려 쓴다. */
  locate(L, f) {
    const d = f * L.total;
    let lo = 0, hi = L.c.length - 1;
    while (lo < hi - 1) {
      const m = (lo + hi) >> 1;
      if (L.c[m] <= d) lo = m; else hi = m;
    }
    const t = (d - L.c[lo]) / (L.c[lo + 1] - L.c[lo] || 1);
    this.spot.x = L.x[lo] + (L.x[lo + 1] - L.x[lo]) * t;
    this.spot.y = L.y[lo] + (L.y[lo + 1] - L.y[lo]) * t;
    this.spot.a = Math.atan2(L.y[lo + 1] - L.y[lo], L.x[lo + 1] - L.x[lo]) * 180 / Math.PI;
    return this.spot;
  }
}
