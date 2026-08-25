/* node tools/icon.mjs > icon/icon.html — 확장 아이콘의 원본 화면을 만든다.
   2호선 순환선의 실제 형상을 쓴다. 그림을 손으로 그리지 않고 데이터에서 뽑는다. */
import fs from 'node:fs';

const net = JSON.parse(fs.readFileSync(new URL('../data/network.json', import.meta.url)));
const by = new Map(net.stations.map((s) => [s.i, s]));
const segs = net.segments.filter((g) => g.l === '2');
const pts = segs.map((g) => (g.g ? g.g.map(([la, lo]) => [lo, la])
  : [[by.get(g.a).lon, by.get(g.a).lat], [by.get(g.b).lon, by.get(g.b).lat]]));

const flat = pts.flat();
const lon = flat.map((p) => p[0]), lat = flat.map((p) => p[1]);
const [x0, x1] = [Math.min(...lon), Math.max(...lon)];
const [y0, y1] = [Math.min(...lat), Math.max(...lat)];
const kx = Math.cos((y0 + y1) / 2 * Math.PI / 180);
const span = Math.max((x1 - x0) * kx, y1 - y0);
const PAD = 14, SIZE = 128;
const s = (SIZE - PAD * 2) / span;
const px = (v) => ((v - x0) * kx * s + PAD + ((SIZE - PAD * 2) - (x1 - x0) * kx * s) / 2).toFixed(1);
const py = (v) => ((y1 - v) * s + PAD + ((SIZE - PAD * 2) - (y1 - y0) * s) / 2).toFixed(1);
const d = pts.map((p) => 'M' + p.map(([a, b]) => `${px(a)} ${py(b)}`).join('L')).join('');

const color = (net.lines.find((l) => l.id === '2') || {}).color || '#00a84d';
process.stdout.write(`<!doctype html><meta charset="utf-8">
<style>html,body{margin:0;background:#0b0f16}svg{display:block}</style>
<svg width="${SIZE}" height="${SIZE}" viewBox="0 0 ${SIZE} ${SIZE}" xmlns="http://www.w3.org/2000/svg">
  <rect width="${SIZE}" height="${SIZE}" rx="26" fill="#0b0f16"/>
  <path d="${d}" fill="none" stroke="${color}" stroke-width="9"
        stroke-linecap="round" stroke-linejoin="round"/>
</svg>
`);
