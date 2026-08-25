/* node tools/selftest.mjs — DOM 없이 확인할 수 있는 것만 본다.

   model 과 vm 은 화면을 모르게 짜 두었으므로 node 에서 그대로 부를 수 있다.
   뷰는 여기서 못 본다 — 그건 브라우저를 띄워서 봐야 한다. */

import { relSec, hhmm, DAY } from '../src/model.js';
import { createVM } from '../src/vm.js';

let bad = 0;
const eq = (got, want, why) => {
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    console.error(`  FAIL  ${why}\n        받은 값 ${JSON.stringify(got)}, 기대 ${JSON.stringify(want)}`);
    bad++;
  }
};

/* 시각 계산 — 열차가 선로 밖으로 나간 사고가 이 자리에서 났다. */
eq(relSec(30000, 18090), 11910, '한낮 — 그냥 뺀 값');
eq(relSec(0, 0), 0, '출발하는 순간');
eq(relSec(0, 90000), 82800, '25:00 출발편은 자정에 아직 안 떴다 (음수가 되면 안 된다)');
eq(relSec(3600, 90000), 0, '25:00 출발편은 01:00 에 출발한다');
eq(relSec(5400, 90000), 1800, '25:00 출발편은 01:30 에 30분째 달린다');
eq(relSec(86340, 90000), 82740, '23:59 에도 25:00 편은 아직 아니다');
eq(relSec(100, 86340), 160, '자정을 넘긴 편은 어제 출발한 것으로 이어진다');
eq(hhmm(0), '00:00', '자정');
eq(hhmm(DAY - 60), '23:59', '하루의 끝');
eq(hhmm(90000), '01:00', '25:00 은 화면에서 01:00 이다');

/* 흐름 상태 — 재생·배속·현재 시각이 서로를 밟지 않는지. */
globalThis.matchMedia = () => ({ matches: true });        // 감속 모드: rAF 대신 타이머
globalThis.requestAnimationFrame = () => 0;
globalThis.cancelAnimationFrame = () => {};
globalThis.fetch = () => Promise.reject(new Error('테스트에서는 안 부른다'));

const holidays = { from: 2026, to: 2028, dates: { '2026-09-24': '추석', '2026-07-17': '제헌절' } };
const p2 = (n) => (n < 10 ? '0' : '') + n;
const model = {
  net: { span: [1899, 2026], lines: [], segments: [], stations: [] },
  leg: () => null, locate: () => null,
  holiday(d) {
    const y = d.getFullYear();
    if (y < holidays.from || y > holidays.to) return null;
    return holidays.dates[`${y}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`] || '';
  },
};
const vm = createVM(model);
const seen = [];
vm.on(['follow', 'playing'], () => seen.push([vm.follow, vm.playing]));
const settle = () => new Promise((r) => setTimeout(r, 0));

eq([vm.follow, vm.playing, vm.flowing], [false, false, false], '처음에는 멈춰 있다');
vm.toNow();
eq([vm.follow, vm.playing, vm.flowing], [true, false, true], '현재 시각 — 따라가는 중');
vm.play();
eq([vm.follow, vm.playing], [false, true], '배속을 켜면 실시간에서 풀린다');
vm.seek(30000);
eq([vm.follow, vm.playing, vm.at], [false, false, 30000], '슬라이더를 끌면 그 자리에 선다');
vm.setRate(120);
eq([vm.rate, vm.flowing], [120, false], '멈춰 있을 때 배속만 고르면 흐르지 않는다');
vm.toNow(); vm.setRate(10);
eq([vm.rate, vm.follow, vm.playing], [10, false, true], '따라가는 중에 배속을 고르면 그 속도로 이어 흐른다');
vm.stop();

/* 오늘 쓸 시간표 — 공휴일이 평일에 걸린 날만 요일과 갈린다. */
const on = (iso) => vm.today(new Date(`${iso}T09:00:00`));
eq(on('2026-09-24'), { day: '3', name: '추석', known: true }, '평일에 걸린 추석은 휴일 시간표');
eq(on('2026-07-17'), { day: '3', name: '제헌절', known: true }, '2026년부터 제헌절도 공휴일이다');
eq(on('2026-09-23'), { day: '1', name: '', known: true }, '그냥 수요일');
eq(on('2026-09-19'), { day: '2', name: '', known: true }, '토요일');
eq(on('2026-09-20'), { day: '3', name: '', known: true }, '일요일');
eq(on('2030-01-01'), { day: '1', name: null, known: false }, '표가 안 덮는 해는 요일로만 — 화면이 그렇게 말해야 한다');

await settle();
if (!seen.length) { console.error('  FAIL  구독자가 한 번도 안 불렸다'); bad++; }

console.log(bad ? `실패 ${bad}건` : '통과');
process.exit(bad ? 1 : 0);
