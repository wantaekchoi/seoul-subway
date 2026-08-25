/* 컨트롤 뷰 — 독크의 버튼·슬라이더와 body 클래스. 상태를 그리기만 하고 바꾸지 않는다.
   누르면 뷰모델의 명령을 부르고, 화면은 그 결과로 바뀐 상태를 보고 다시 그린다. */

import { DAY, hhmm } from '../model.js';

export function chrome(model, el, vm) {
  // on() 은 등록하면서 바로 한 번 부른다. 콜백이 읽는 값은 그전에 만들어 둔다.
  const untimed = model.net.lines.filter((l) => !vm.timed(l.id)).length;
  el.untimed.hidden = !untimed;

  // 공휴일은 날짜 규칙으로 안 나온다 — 설·추석은 음력이고 대체·임시공휴일은 그해
  // 정해진다. 구워 둔 표가 오늘을 덮는지 아닌지를 화면이 그대로 말한다.
  const t = vm.today();
  const h = model.holidays;
  el.holiday.textContent =
    !h ? '공휴일은 요일로 가리지 못합니다. 휴일 시간표는 직접 선택해 주세요.'
    : !t.known ? `공휴일 표가 ${h.to}년까지라 그 뒤로는 요일로만 고릅니다. 휴일 시간표는 직접 선택해 주세요.`
    : t.name ? `오늘은 ${t.name}이라 휴일 시간표로 시작합니다.`
    : `공휴일은 자동으로 가립니다. 표는 ${h.to}년까지 있습니다.`;

  el.modes.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b && b.dataset.mode !== vm.mode) vm.setMode(b.dataset.mode);
  });
  el.play.addEventListener('click', () => (vm.flowing ? vm.stop() : vm.play()));
  el.tonow.addEventListener('click', () => vm.toNow());
  el.rate.addEventListener('change', () => vm.setRate(+el.rate.value));
  el.day.addEventListener('change', () => vm.setDay(el.day.value));
  el.slider.addEventListener('input', () => vm.seek(+el.slider.value));
  el.untimed.addEventListener('click', () => vm.toggleUntimed());

  vm.on(['mode'], () => {
    document.body.classList.remove('live', 'year');
    document.body.classList.add(vm.mode);
    for (const b of el.modes.children) b.setAttribute('aria-pressed', b.dataset.mode === vm.mode);
    const [lo, hi, step] = vm.span[vm.mode];
    el.slider.min = lo; el.slider.max = hi; el.slider.step = step;
    el.slider.setAttribute('aria-label', vm.mode === 'live' ? '시각' : '연도');
    el.play.title = vm.mode === 'live' ? '시간 흐름 재생 · 일시정지' : '연표 재생';
  });

  vm.on(['follow', 'playing'], () => {
    el.play.textContent = vm.flowing ? '⏸' : '▶';
    el.play.setAttribute('aria-label', vm.flowing ? '일시정지' : '재생');
    document.body.classList.toggle('following', vm.follow);
  });

  vm.on(['at', 'mode'], () => {
    const label = vm.mode === 'live' ? hhmm(vm.at) : String(Math.floor(vm.at));
    el.tag.value = label;
    el.slider.value = vm.at;
  });

  vm.on(['rate'], () => { el.rate.value = String(vm.rate); });
  vm.on(['day'], () => { el.day.value = vm.day; });
  vm.on(['showUntimed'], () => {
    document.body.classList.toggle('show-untimed', vm.showUntimed);
    el.untimed.textContent = vm.showUntimed ? '시간표 없는 노선 숨기기' : `시간표 없는 노선 ${untimed}개 보기`;
  });

}
