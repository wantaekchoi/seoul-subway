/* 머리말 뷰 — 큰 시계와 그 아래 한 줄. 지금 무엇을 보고 있는지만 말한다. */

import { hhmm } from '../model.js';

export function header(model, el, vm, stat) {
  vm.on(['at', 'mode', 'table', 'follow', 'error'], () => {
    if (vm.error) { el.sub.textContent = vm.error; return; }
    if (vm.mode === 'year') {
      el.big.textContent = Math.floor(vm.at);
      el.sub.innerHTML = `<b>${stat.nSta}</b>개 역 · <b>${stat.nSeg}</b>개 구간`;
      el.note.hidden = true;
      return;
    }
    el.big.textContent = hhmm(vm.at);
    const n = vm.frame.n;
    el.sub.innerHTML = vm.table
      ? (vm.follow ? '실시간 · ' : '') + `운행 중 <b>${n}</b>편`
      : '시간표 불러오는 중…';
    el.note.hidden = !vm.table || n > 0;
    if (vm.table && !n) el.note.textContent = `운행 종료 · 첫차 ${hhmm(vm.frame.firstRun)}`;
  });
}
