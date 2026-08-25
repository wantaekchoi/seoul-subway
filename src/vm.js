/* 뷰모델 — 화면이 무엇을 보여 줄지를 정하는 상태와, 그 상태를 바꾸는 명령.
   DOM 을 모른다. 여기서 값을 바꾸면 그 값을 구독한 뷰만 다시 그려진다.

   왜 이렇게 두는가: 예전에는 재생 글리프를 세 군데서, `following` 클래스를 두
   군데서 각자 썼다. 상태를 하나 늘릴 때마다 손댈 곳이 늘고, 한 곳을 빠뜨리면
   화면이 서로 다른 말을 했다. 쓰는 곳은 여기 하나, 그리는 곳은 뷰 하나로 둔다. */

import { DAY, DWELL, TURN, TIMED, relSec, grab } from './model.js';

const RATE0 = 1;        // 배속 기본값. 실시간과 같은 속도다.
const YEAR_RUN = 26;    // 연표를 처음부터 끝까지 훑는 시간(초)
const MAX_TRAINS = 2048;

// 매 프레임 벽시계를 다시 읽는다. 흘러간 시간을 더해 나가지 않으므로 어긋날 데가 없다 —
// 탭이 멈춰 있다 돌아와도 그 순간의 시각으로 붙는다. 밀리초까지 읽어야 초마다 끊기지 않는다.
export const wallSecs = () => {
  const d = new Date();
  return d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds() + d.getMilliseconds() / 1000;
};

export function createVM(model) {
  const span = { live: [0, DAY - 60, 60], year: [model.net.span[0], model.net.span[1], 0.05] };

  const state = {
    mode: 'live',       // 'live' | 'year'
    at: 0,              // live 면 초, year 면 연도
    follow: false,      // 벽시계를 따라가는 중인가
    playing: false,     // 배속으로 흐르는 중인가
    rate: RATE0,
    day: '1',           // 평일 1 · 토 2 · 휴일 3
    table: null,        // 그 요일 시간표
    pick: null,         // 하이라이트한 노선 id
    showUntimed: false, // 시간표 없는 노선을 곁 화면에 펼쳐 두었나
    error: '',
  };

  const subs = [];
  let dirty = new Set(), queued = false;

  /** keys 중 하나라도 바뀌면 fn(vm) 을 부른다. 처음 한 번은 즉시 부른다. */
  function on(keys, fn) {
    subs.push({ keys: new Set(keys), fn });
    fn(vm);
  }

  function flush() {
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      const changed = dirty; dirty = new Set();
      if (changed.has('at') || changed.has('table') || changed.has('mode')) frame();
      for (const s of subs) {
        for (const k of changed) if (s.keys.has(k)) { s.fn(vm); break; }
      }
    });
  }

  const vm = new Proxy(state, {
    set(t, k, v) {
      if (t[k] !== v) { t[k] = v; dirty.add(k); flush(); }
      return true;
    },
  });

  /* ------------------------------------------------------------ 파생 */

  // 열차 자리는 매 프레임 다시 구한다. 자리를 미리 잡아 두고 덮어써서 프레임마다
  // 새 객체를 만들지 않는다.
  const buf = {
    n: 0,
    x: new Float64Array(MAX_TRAINS),
    y: new Float64Array(MAX_TRAINS),
    a: new Float64Array(MAX_TRAINS),
    line: new Array(MAX_TRAINS),
    running: new Map(),
    firstRun: Infinity,
  };

  function frame() {
    buf.running.clear();
    buf.n = 0;
    if (state.mode !== 'live' || !state.table) return;
    for (const tr of state.table) {
      const rel = relSec(state.at, tr.t);
      if (rel > tr.z) continue;
      const o = tr.o, s = tr.s;
      if (s.length < 2) continue;
      let lo = 0, hi = o.length - 1;
      while (lo < hi) {
        const m = (lo + hi + 1) >> 1;
        if (o[m] <= rel) lo = m; else hi = m - 1;
      }
      let ang, spot;
      if (lo >= s.length - 1) {
        const L = model.leg(tr.l, s[s.length - 2], s[s.length - 1]);
        if (!L) continue;
        spot = model.locate(L, 1);
        ang = spot.a + 180 * (rel - o[o.length - 1]) / TURN;   // 종점에서 몸을 돌린다
      } else {
        const L = model.leg(tr.l, s[lo], s[lo + 1]);
        if (!L) continue;
        const dur = o[lo + 1] - o[lo];
        const move = Math.max(1, dur - Math.min(DWELL, dur * 0.4));
        spot = model.locate(L, Math.min(1, (rel - o[lo]) / move));  // 역에 닿으면 잠깐 멈춘다
        ang = spot.a;
      }
      if (buf.n >= MAX_TRAINS) break;
      const i = buf.n++;
      buf.x[i] = spot.x; buf.y[i] = spot.y; buf.a[i] = ang; buf.line[i] = tr.l;
      buf.running.set(tr.l, (buf.running.get(tr.l) || 0) + 1);
    }
  }

  /* ------------------------------------------------------------ 명령 */

  let raf = 0, beat = 0, prev = 0;
  // 감속을 켠 사람에게는 매 프레임 대신 5초마다 자리만 옮긴다. 실시간이 1배속이라
  // 그 사이 움직임은 어차피 눈에 안 띈다.
  const smooth = !matchMedia('(prefers-reduced-motion: reduce)').matches;

  function tick(ts) {
    if (state.follow) { vm.at = wallSecs(); raf = requestAnimationFrame(tick); return; }
    if (!state.playing) return;
    const dt = prev ? Math.min(ts - prev, 250) : 16;
    prev = ts;
    if (state.mode === 'live') {
      vm.at = (state.at + dt / 1000 * state.rate) % DAY;
    } else {
      const next = state.at + dt / 1000 * (span.year[1] - span.year[0]) / YEAR_RUN;
      if (next >= span.year[1]) { vm.at = span.year[1]; api.stop(); return; }
      vm.at = next;
    }
    raf = requestAnimationFrame(tick);
  }

  const api = {
    span,

    /** 오늘 쓸 시간표. 공휴일 표가 오늘을 덮으면 그걸 보고, 아니면 요일로만 고른다.
        name 은 공휴일 이름, 공휴일이 아니면 '', 표가 그 해를 안 덮으면 null. */
    today(d = new Date()) {
      const name = model.holiday(d);
      const wd = d.getDay();
      let day = '1';
      if (name || wd === 0) day = '3';
      else if (wd === 6) day = '2';
      return { day, name, known: name !== null };
    },
    get flowing() { return state.follow || state.playing; },
    get frame() { return buf; },
    /** 시간표가 있는 노선인가 — 곁 화면이 이걸로 접을 줄을 고른다. */
    timed: (id) => TIMED.test(id),
    on,

    /** 흐름을 멈춘다. 실시간 추종이든 배속 재생이든 그 시각에 그대로 선다. */
    stop() {
      cancelAnimationFrame(raf); clearInterval(beat); beat = 0;
      vm.follow = false; vm.playing = false;
    },

    /** 고른 배속으로 시간을 흘린다. 실시간에서는 풀린다. */
    play() {
      if (state.mode === 'year' && state.at >= span.year[1]) vm.at = span.year[0];
      api.stop();
      prev = 0;
      vm.playing = true;
      raf = requestAnimationFrame(tick);
    },

    /** 지금 시각으로 돌아가 벽시계를 따라간다. */
    toNow() {
      api.stop();
      vm.follow = true;
      vm.at = wallSecs();
      if (smooth) raf = requestAnimationFrame(tick);
      else beat = setInterval(() => { vm.at = wallSecs(); }, 5000);
    },

    /** 슬라이더로 그 시점에 세운다. */
    seek(t) { api.stop(); vm.at = t; },

    setMode(next, at) {
      api.stop();
      vm.mode = next;
      if (next === 'live') { if (at == null) api.toNow(); else vm.at = at; }
      else vm.at = at == null ? span.year[1] : at;
    },

    setRate(r) {
      vm.rate = r;
      // 배속을 고른 것 자체가 "이 속도로 보겠다" 는 뜻이다. 흐르던 중이면 이어서 흐른다.
      if (api.flowing) api.play();
    },

    /** 한 노선만 남기고 흐리게. 같은 줄을 다시 누르면 전부 되돌린다. */
    togglePick(l) { vm.pick = state.pick === l ? null : l; },
    toggleUntimed() { vm.showUntimed = !state.showUntimed; },

    setDay(d) {
      vm.day = d;
      vm.table = null;
      const got = cache.get(d);
      if (got) { vm.table = got; return; }
      grab(`data/timetable-${d}.json`).then((list) => {
        for (const tr of list) tr.z = tr.o[tr.o.length - 1] + TURN;
        cache.set(d, list);
        if (state.day === d) { buf.firstRun = list.reduce((m, t) => Math.min(m, t.t), Infinity); vm.table = list; }
      }).catch((e) => { vm.error = `시간표를 불러오지 못했습니다: ${e.message}`; });
    },
  };
  const cache = new Map();

  return new Proxy(api, {
    get: (t, k) => (k in t ? t[k] : state[k]),
    set: (t, k, v) => { vm[k] = v; return true; },
  });
}
