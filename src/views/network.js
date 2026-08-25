/* 노선망 뷰 — 구간과 역이 언제 보이고 언제 흐려지는지만 맡는다.
   연표 진행(mode·at)과 하이라이트(pick) 둘 다 같은 요소를 건드리므로 한 곳에 둔다. */

import { FRESH } from '../model.js';

export function network(model, st, vm) {
  const { net } = model;
  const { segEl, staEl, gSeg, gSta } = st;
  // 연표가 어디까지 왔는지. 머리말과 곁 화면이 같은 숫자를 봐야 하므로 여기서 한 번만 센다.
  const stat = { counts: new Map(net.lines.map((l) => [l.id, 0])), nSta: 0, nSeg: 0 };
  const lineOpen = stat.counts;
  let nSta = 0, nSeg = 0, freshFrom = 0, was = null;

  function allOn(on) {
    for (let i = 0; i < segEl.length; i++) {
      segEl[i].classList.toggle('on', on);
      segEl[i].style.strokeDashoffset = on ? 0 : net.segments[i]._len;
    }
    for (const c of staEl) { c.classList.toggle('on', on); c.classList.remove('fresh'); }
    nSta = nSeg = freshFrom = 0;
    for (const id of lineOpen.keys()) lineOpen.set(id, 0);
  }

  /** 연표를 t 시점까지 감는다. 훑고 지나간 만큼만 손대므로 매 프레임 전수는 아니다. */
  function toYear(t) {
    let s = 0; while (s < model.staAge.length && net.stations[model.staAge[s]].t <= t) s++;
    let g = 0; while (g < model.segAge.length && net.segments[model.segAge[g]].t <= t) g++;

    for (let i = Math.min(s, nSta); i < Math.max(s, nSta); i++) {
      staEl[model.staAge[i]].classList.toggle('on', i < s);
    }
    for (let i = Math.min(g, nSeg); i < Math.max(g, nSeg); i++) {
      const on = i < g, j = model.segAge[i];
      segEl[j].classList.toggle('on', on);
      segEl[j].style.strokeDashoffset = on ? 0 : net.segments[j]._len;
      const l = net.segments[j].l;
      lineOpen.set(l, lineOpen.get(l) + (on ? 1 : -1));
    }

    // 갓 열린 역만 강조한다.
    if (s < freshFrom) freshFrom = s;
    while (freshFrom < s && t - net.stations[model.staAge[freshFrom]].t >= FRESH) {
      staEl[model.staAge[freshFrom]].classList.remove('fresh');
      freshFrom++;
    }
    for (let i = freshFrom; i < s; i++) staEl[model.staAge[i]].classList.add('fresh');
    nSta = stat.nSta = s; nSeg = stat.nSeg = g;
  }

  /** 고른 노선만 남기고 흐리게. 고른 게 없으면 전부 되돌린다. */
  function paintPick(pick) {
    const on = pick ? model.staOfLine.get(pick) : null;
    document.body.classList.toggle('picked', !!pick);
    for (const p of gSeg.children) p.classList.toggle('off', !!pick && p.dataset.l !== pick);
    for (const c of gSta.children) c.classList.toggle('off', !!on && !on.has(+c.dataset.i));
  }

  vm.on(['mode', 'at'], () => {
    if (vm.mode !== was) { allOn(vm.mode === 'live'); was = vm.mode; }
    if (vm.mode === 'year') toYear(vm.at);
  });
  vm.on(['pick'], () => paintPick(vm.pick));

  return stat;
}
