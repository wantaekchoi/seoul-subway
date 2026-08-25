/* 열차 뷰 — 뷰모델이 구해 둔 자리를 그리기만 한다. 어디에 있어야 하는지는 계산하지 않는다. */

import { svg } from './stage.js';

// 코가 +x 를 향하는 삼각형. 선끝·꼭짓점을 둥글게 하는 건 stroke-linejoin 이 한다.
const TRAIN_D = 'M3.5 0L-2.3 2.4L-2.3 -2.4Z';

export function trains(model, st, vm) {
  const pool = [], hue = [], dim = [];
  let live = 0;

  function paint() {
    const f = vm.frame, pick = vm.pick;
    const k = st.cam.scale;
    for (let i = 0; i < f.n; i++) {
      let p = pool[i];
      if (!p) {
        p = svg('path');
        p.setAttribute('d', TRAIN_D);
        st.gTrain.appendChild(p);
        pool[i] = p;
      }
      p.setAttribute('transform',
        `translate(${f.x[i].toFixed(1)} ${f.y[i].toFixed(1)}) rotate(${f.a[i].toFixed(0)}) scale(${k})`);
      const color = model.color(f.line[i]);
      if (hue[i] !== color) {
        p.setAttribute('fill', color); p.setAttribute('stroke', color);
        hue[i] = color;
      }
      const off = !!pick && f.line[i] !== pick;
      if (dim[i] !== off) { p.classList.toggle('off', off); dim[i] = off; }
    }
    for (let i = f.n; i < live; i++) pool[i].style.display = 'none';
    for (let i = live; i < f.n; i++) pool[i].style.display = '';
    live = f.n;
  }

  vm.on(['at', 'mode', 'table', 'pick'], paint);
  st.cam.onZoom = paint;   // 확대하면 크기만 다시 맞춘다
  return { paint };
}
