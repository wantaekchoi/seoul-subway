#!/usr/bin/env bash
# 크롬 새 탭 확장으로 묶는다.  ./tools/pack-newtab.sh
#
# 페이지가 정적 파일뿐이라 옮겨 담는 게 전부다. 굽는 도구·배경지도 원본·문서는 빼고
# 화면이 실제로 읽는 것만 넣는다. 결과는 dist/ 와 dist.zip 이고 둘 다 gitignore 다.
#
# 확인: 크롬 → 확장 프로그램 → 개발자 모드 → 압축해제된 확장 프로그램을 로드 → dist/
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf dist dist.zip
mkdir -p dist
cp manifest.json newtab.html newtab.js style.css LICENSE dist/
cp -R src icon dist/
mkdir -p dist/data
# 화면이 fetch 하는 것만. .station_map.json 은 시간표를 구울 때만 쓴다.
cp data/network.json data/basemap.topo.json data/holidays.json dist/data/
cp data/timetable-1.json data/timetable-2.json data/timetable-3.json dist/data/
rm -f dist/icon/icon.html   # 아이콘 원본 화면은 굽는 데만 쓴다

( cd dist && zip -qr ../dist.zip . )
printf '%s\n' "dist/ · $(find dist -type f | wc -l | tr -d ' ')개 파일 · zip $(du -h dist.zip | cut -f1)"
