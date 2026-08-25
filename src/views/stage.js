/* 무대 — SVG 뼈대를 세우고 카메라(확대·이동)와 역 이름표를 맡는다.
   여기서 만든 요소들을 network·trains 뷰가 나눠 그린다. */

const NS = 'http://www.w3.org/2000/svg';
export const svg = (name) => document.createElementNS(NS, name);

const BASE_SW = 2.4, BASE_DOT = 2.2, BASE_TRAIN = 1.25;

export function stage(model, el) {
  const { net, topo } = model;

  // 바다는 폴리곤이 없다. 땅만 칠하고 나머지는 바탕으로 둔다 — 북한도 같은 바탕이라
  // 물로 칠해지지 않는다. 노선망 북쪽 끝 위는 잘라 낸다.
  const defs = svg('defs');
  const clip = svg('clipPath'); clip.id = 'north';
  const box = svg('rect');
  box.setAttribute('x', -9000); box.setAttribute('y', 0);
  box.setAttribute('width', 18000); box.setAttribute('height', 9000);
  clip.appendChild(box); defs.appendChild(clip); el.map.appendChild(defs);

  const arcs = topo.arcs.map((a) => {
    const [sx, sy] = topo.transform.scale, [tx, ty] = topo.transform.translate;
    let x = 0, y = 0;
    return a.map(([dx, dy]) => {
      x += dx; y += dy;
      return model.px(x * sx + tx).toFixed(1) + ' ' + model.py(y * sy + ty).toFixed(1);
    });
  });

  function shape(name) {
    const ring = (idx) => {
      const out = [];
      for (const i of idx) {
        const a = i < 0 ? arcs[~i].slice().reverse() : arcs[i];
        for (let k = out.length ? 1 : 0; k < a.length; k++) out.push(a[k]);
      }
      return 'M' + out.join('L') + 'Z';
    };
    let d = '';
    for (const g of topo.objects[name].geometries) {
      const polys = g.type === 'Polygon' ? [g.arcs] : g.type === 'MultiPolygon' ? g.arcs : [];
      for (const p of polys) for (const r of p) d += ring(r);
    }
    const path = svg('path');
    path.id = name === 'sigungu' ? 'land' : 'water';
    path.setAttribute('d', d);
    return path;
  }

  const gBase = svg('g'); gBase.id = 'basemap';
  gBase.setAttribute('clip-path', 'url(#north)');
  gBase.append(shape('sigungu'), shape('water'));

  const gSeg = svg('g'); gSeg.id = 'segments';
  const gSta = svg('g'); gSta.id = 'stations';
  const gTrain = svg('g'); gTrain.id = 'trains';
  el.map.append(gBase, gSeg, gSta, gTrain);

  const segEl = net.segments.map((g) => {
    const p = svg('path');
    p.setAttribute('d', 'M' + model.pts(g).map((q) => q[0].toFixed(1) + ' ' + q[1].toFixed(1)).join('L'));
    p.setAttribute('stroke', model.color(g.l));
    p.dataset.l = g.l;
    p.style.strokeDasharray = g._len;
    gSeg.appendChild(p);
    return p;
  });

  const staEl = net.stations.map((s) => {
    const c = svg('circle');
    c.setAttribute('cx', s.x.toFixed(1)); c.setAttribute('cy', s.y.toFixed(1));
    c.dataset.i = s.i;
    gSta.appendChild(c);
    return c;
  });

  /* ---------------------------------------------------------------- 카메라 */
  // 1호선은 남으로 신창, 북으로 소요산까지 간다. 그걸 다 넣으면 서울 도심이 화면의
  // 한 줌으로 뭉쳐 열차가 1~2px 삼각형이 된다. 2호선 순환선이 감싸는 만큼으로 시작하고
  // 축소하면 나머지 수도권이 그대로 나온다.
  function core() {
    const on = model.staOfLine.get('2');
    if (!on || on.size < 2) return null;
    const xs = [], ys = [];
    for (const i of on) { const s = model.byId.get(i); if (s) { xs.push(s.x); ys.push(s.y); } }
    const m = 40;   // 순환선 바로 밖 환승역까지는 보이게
    return { x: Math.min(...xs) - m, y: Math.min(...ys) - m,
             w: Math.max(...xs) - Math.min(...xs) + m * 2,
             h: Math.max(...ys) - Math.min(...ys) + m * 2 };
  }

  // 화면 비율에 맞춰 짧은 쪽을 늘린다. 안 그러면 meet 이 남는 쪽을 여백으로 두고
  // 그 자리에 노선 없는 배경만 비친다.
  function fit(b) {
    const r = el.map.getBoundingClientRect();
    if (!r.width || !r.height) return b;
    const want = r.width / r.height;
    if (b.w / b.h < want) { const w = b.h * want; return { x: b.x - (w - b.w) / 2, y: b.y, w, h: b.h }; }
    const h = b.w / want;
    return { x: b.x, y: b.y - (h - b.h) / 2, w: b.w, h };
  }

  // 축소 한계이자 선·열차 굵기의 기준. 화면 비율을 먹였으므로 world.w 와는 다르다.
  const full = fit({ x: 0, y: 0, w: model.world.w, h: model.world.h });
  const vb = { ...(core() ? fit(core()) : full) };
  el.map.setAttribute('preserveAspectRatio', 'xMidYMin meet');

  const cam = { k: 1, onZoom: () => {} };

  function view() {
    el.map.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
    // 확대해도 선·점·열차가 같이 커지지 않게 되돌린다.
    cam.k = vb.w / full.w;
    const root = document.documentElement.style;
    root.setProperty('--sw', (BASE_SW * cam.k).toFixed(2));
    root.setProperty('--dot', (BASE_DOT * cam.k).toFixed(2));
    cam.scale = BASE_TRAIN * cam.k;
  }
  view();

  // 화면 좌표를 뷰박스 좌표로. preserveAspectRatio=meet 이라 짧은 쪽에 여백이 생긴다.
  function toWorld(cx, cy) {
    const r = el.map.getBoundingClientRect();
    const s = Math.min(r.width / vb.w, r.height / vb.h);
    return {
      s,
      x: vb.x + (cx - r.left - (r.width - vb.w * s) / 2) / s,
      y: vb.y + (cy - r.top) / s,
    };
  }

  function zoomAt(cx, cy, factor) {
    const u = toWorld(cx, cy);
    const next = Math.min(full.w, Math.max(full.w / 60, vb.w * factor));
    const f = next / vb.w;
    vb.x = u.x - (u.x - vb.x) * f;
    vb.y = u.y - (u.y - vb.y) * f;
    vb.w *= f; vb.h *= f;
    view();
    cam.onZoom();
  }

  el.map.addEventListener('wheel', (e) => {
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, Math.exp(e.deltaY * 0.0015));
  }, { passive: false });

  const grip = new Map();
  let pinch = 0;
  el.map.addEventListener('pointerdown', (e) => {
    el.map.setPointerCapture(e.pointerId);
    grip.set(e.pointerId, { x: e.clientX, y: e.clientY });
    el.map.classList.add('dragging');
  });
  el.map.addEventListener('pointermove', (e) => {
    const was = grip.get(e.pointerId);
    if (!was) return;
    grip.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (grip.size === 2) {
      const [a, b] = [...grip.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinch) zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, pinch / d);
      pinch = d;
    } else {
      const s = toWorld(0, 0).s;
      vb.x -= (e.clientX - was.x) / s;
      vb.y -= (e.clientY - was.y) / s;
      view();
    }
  });
  for (const name of ['pointerup', 'pointercancel']) {
    el.map.addEventListener(name, (e) => {
      grip.delete(e.pointerId);
      if (grip.size < 2) pinch = 0;
      if (!grip.size) el.map.classList.remove('dragging');
    });
  }

  /* ---------------------------------------------------------------- 역 이름표 */
  gSta.addEventListener('pointerover', (e) => {
    const c = e.target.closest && e.target.closest('circle');
    if (!c) return;
    const s = model.byId.get(+c.dataset.i);
    el.tip.innerHTML = '<b></b><span></span>';
    el.tip.querySelector('b').textContent = s.n;
    el.tip.querySelector('span').textContent = s.o || '—';
    const r = c.getBoundingClientRect();
    el.tip.style.left = `${r.left + r.width / 2}px`;
    el.tip.style.top = `${r.top}px`;
    el.tip.hidden = false;
  });
  gSta.addEventListener('pointerout', () => { el.tip.hidden = true; });

  return { gSeg, gSta, gTrain, segEl, staEl, cam };
}
