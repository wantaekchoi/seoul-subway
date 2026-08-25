#!/usr/bin/env bash
# 크롬 새 탭 확장으로 묶는다.
#
#   ./tools/pack-newtab.sh          다시 묶기만 한다
#   ./tools/pack-newtab.sh --bump   끝자리 버전을 올리고 묶는다 (스토어에 올릴 때)
#
# 페이지가 정적 파일뿐이라 옮겨 담는 게 전부다. 굽는 도구·배경지도 원본·문서는 빼고
# 화면이 실제로 읽는 것만 넣는다. 결과는 dist/ 와 dist.zip 이고 둘 다 gitignore 다.
#
# 확인: 크롬 → 확장 프로그램 → 개발자 모드 → 압축해제된 확장 프로그램을 로드 → dist/
#
# 데이터를 갱신하려면 먼저:
#   python3 tools/timetable.py --refresh   시간표가 바뀌었을 때
#   python3 tools/holidays.py              공휴일 표가 끝나기 전에 (지금 2028년까지)
set -euo pipefail
cd "$(dirname "$0")/.."

# 스토어는 같은 버전을 다시 받지 않는다. 올릴 때는 --bump 로 끝자리를 올린다.
if [ "${1:-}" = "--bump" ]; then
  python3 tools/bump.py
fi

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
V=$(python3 -c "import json;print(json.load(open('manifest.json'))['version'])")
printf 'v%s · dist/ %s개 파일 · zip %s\n' \
  "$V" "$(find dist -type f | wc -l | tr -d ' ')" "$(du -h dist.zip | cut -f1)"
