# 수도권 전철

https://wantaekchoi.github.io/seoul-subway/

지금 이 시각에 열차가 어디에 있는지를 시간표대로 그립니다. 연표로 바꾸면 1899년
경인선부터 노선망이 자라나는 과정을 봅니다.

## 출처

- 노선 형상·물길 — [OpenStreetMap](https://www.openstreetmap.org/copyright) 기여자, ODbL
- 역 개통일 — [Wikidata](https://www.wikidata.org), CC0
- 시군구 경계 — 통계청 SGIS, 공공누리 제1유형
- 1~9호선 열차 시간표 — 서울특별시 공공데이터([열린데이터광장](https://data.seoul.go.kr))
- 공휴일 — 한국천문연구원 특일 정보(data.go.kr)

`data/` 는 위에서 받아 구운 것이고, 굽는 절차는 `tools/` 에 있습니다. 페이지가
열린 뒤에 부르는 API 는 없습니다.

크롬 새 탭으로도 쓸 수 있습니다. `./tools/pack-newtab.sh` 로 묶은 뒤 확장 프로그램
페이지에서 개발자 모드로 `dist/` 를 불러오면 됩니다.

코드는 MIT, 데이터는 각 출처의 조건을 따릅니다.
