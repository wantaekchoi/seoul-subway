/* 새 탭 화면. 같은 model·vm 을 쓰고 뷰만 줄인다 — 지도와 시계만 남기고 조작은 뺀다.
   탭을 열 때마다 보는 화면이라 만지는 것보다 지금이 어떤지가 먼저다. */

import { load } from './src/model.js';
import { createVM } from './src/vm.js';
import { stage } from './src/views/stage.js';
import { network } from './src/views/network.js';
import { trains } from './src/views/trains.js';
import { header } from './src/views/header.js';

const $ = (id) => document.getElementById(id);
const el = {
  map: $('map'), tip: $('tip'), big: $('big'), sub: $('sub'),
  note: $('note'), loading: $('loading'),
};

load()
  .then((model) => {
    el.loading.hidden = true;
    const st = stage(model, el);
    const vm = createVM(model);
    const stat = network(model, st, vm);   // 연표를 안 쓰므로 값은 안 읽히지만 구독은 필요하다
    trains(model, st, vm);
    header(model, el, vm, stat);
    vm.setDay(vm.today().day);
    vm.setMode('live');                    // 곧장 실시간에 붙는다
  })
  .catch((e) => {
    el.loading.hidden = false;
    el.loading.textContent = `화면을 띄우지 못했습니다: ${e.message}`;
    throw e;
  });
