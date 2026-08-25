/* 곁 화면 뷰 — 노선 목록과 최근 개통. 줄을 누르면 그 노선만 남는다. */

export function panel(model, el, vm, stat) {
  const rowOf = new Map();
  for (const l of model.net.lines) {
    const li = document.createElement('li');
    li.innerHTML = '<button class="row" type="button"><i class="chip"></i>'
                 + '<span class="nm"></span><span class="ct"></span></button>';
    li.querySelector('.chip').style.background = model.color(l.id);
    li.querySelector('.nm').textContent = model.name(l.id);
    li.querySelector('.row').dataset.l = l.id;
    li.classList.toggle('untimed', !vm.timed(l.id));
    el.lines.appendChild(li);
    rowOf.set(l.id, li);
  }

  el.lines.addEventListener('click', (e) => {
    const b = e.target.closest('.row');
    if (b) vm.togglePick(b.dataset.l);
  });

  const undated = model.net.stations.filter((s) => s.t == null);
  el.undated.textContent = undated.length
    ? `개통일 미상 ${undated.length}개 — ${undated.map((s) => s.n).join(', ')}`
    : '';

  vm.on(['at', 'mode', 'table', 'pick'], () => {
    const live = vm.mode === 'live';
    for (const [id, li] of rowOf) {
      const n = live ? (vm.frame.running.get(id) || 0) : stat.counts.get(id);
      li.classList.toggle('on', n > 0);
      li.classList.toggle('pick', id === vm.pick);
      li.querySelector('.ct').textContent =
        live ? (vm.table && vm.timed(id) ? n : '—') : (n || '');
    }
    if (live) return;

    const shown = model.staAge.slice(Math.max(0, stat.nSta - 7), stat.nSta).reverse();
    el.recent.replaceChildren(...shown.map((i) => {
      const st = model.net.stations[i];
      const li = document.createElement('li');
      if (vm.at - st.t < 1) li.className = 'new';
      li.innerHTML = '<i class="chip"></i><span class="nm"></span><span class="dt"></span>';
      li.querySelector('.chip').style.background = model.color(model.homeLine.get(st.i));
      li.querySelector('.nm').textContent = st.n;
      li.querySelector('.dt').textContent = st.o;
      return li;
    }));
  });
}
