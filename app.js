/* 수도권 전철 — 지금 이 시각에 열차가 어디에 있는지를 시간표대로 그린다.
   data/ 에 구워 둔 것만 읽는다. 런타임 API 호출은 없다.

   구조는 셋으로 나눠 둔다.
     src/model.js   구운 데이터와 색인·기하. 화면을 모른다.
     src/vm.js      화면이 무엇을 보여 줄지 정하는 상태와 명령. DOM 을 모른다.
     src/views/*    상태 조각을 구독해 자기 자리만 그린다. 한 DOM 구역에 뷰 하나. */

import { load } from './src/model.js';
import { createVM } from './src/vm.js';
import { stage } from './src/views/stage.js';
import { network } from './src/views/network.js';
import { trains } from './src/views/trains.js';
import { header } from './src/views/header.js';
import { panel } from './src/views/panel.js';
import { chrome } from './src/views/chrome.js';

const $ = (id) => document.getElementById(id);
const el = {
  map: $('map'), tip: $('tip'), big: $('big'), sub: $('sub'), note: $('note'),
  lines: $('lines'), recent: $('recent'), undated: $('undated'), untimed: $('untimed'),
  holiday: $('holiday'), bare: $('bare'),
  tonow: $('tonow'), rate: $('rate'), play: $('play'), slider: $('slider'),
  tag: $('tag'), day: $('day'), modes: $('modes'), loading: $('loading'),
};

load()
  .then(boot)
  .catch((e) => {
    el.loading.hidden = false;
    el.loading.textContent = `화면을 띄우지 못했습니다: ${e.message}`;
    throw e;   // 콘솔에도 남긴다 — 조용히 반쯤 그려진 채로 멈추는 게 제일 나쁘다
  });

function boot(model) {
  el.loading.hidden = true;
  const st = stage(model, el);
  const vm = createVM(model);

  // 등록 순서가 곧 그리는 순서다. 연표 진행을 먼저 세어 두어야 머리말과 곁 화면이
  // 같은 숫자를 본다.
  const stat = network(model, st, vm);
  trains(model, st, vm);
  header(model, el, vm, stat);
  panel(model, el, vm, stat);
  chrome(model, el, vm);

  vm.setDay(vm.today().day);

  // #08:20 은 그 시각, #1974 는 그해가 끝난 시점. 둘 다 재생하지 않고 멈춰 선다.
  const h = decodeURIComponent(location.hash.slice(1));
  const at = /^(\d{1,2}):(\d{2})$/.exec(h);
  const yr = parseFloat(h);
  const [lo, hi] = vm.span.year;

  if (at) vm.setMode('live', (+at[1] * 60 + +at[2]) * 60);
  else if (Number.isFinite(yr) && yr >= lo && yr <= hi) {
    vm.setMode('year', Math.min(yr + 0.95, hi));   // 슬라이더 step 격자 위
  } else vm.setMode('live');   // 기본은 실시간이다
}
