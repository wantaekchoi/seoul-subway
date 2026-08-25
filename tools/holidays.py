#!/usr/bin/env python3
"""공휴일 날짜를 한국천문연구원 특일정보에서 받아 data/holidays.json 으로 굽는다.

지하철 시간표가 평일·토요일·휴일 세 벌인데 브라우저는 그 날짜가 공휴일인지 모른다.
설·추석은 음력이고 대체·임시공휴일은 그해 정해져서 날짜 규칙으로는 안 나온다.

인증키는 레포에 두지 않는다. 환경변수 DATA_GO_KR_KEY 를 먼저 보고, 없으면 macOS
키체인에서 `data-go-kr-key` 를 꺼낸다. data.go.kr 에서 자동승인으로 발급한다.

받는 해는 API 가 주는 만큼이다. 2026 년 기준으로 2028 년까지 나오고 그 뒤는 빈다 —
화면은 표가 끝나는 해를 말하고, 그 뒤로는 요일로만 고른다.

주의: 2026 년부터 제헌절이 공휴일로 재지정됐고 근로자의 날도 노동절로 바뀌며 공휴일이
됐다. 손으로 거르지 않는다 — 규정이 바뀌면 이 API 가 먼저 안다.
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
SOURCE = "한국천문연구원 특일 정보 (data.go.kr)"


def key():
    k = os.environ.get("DATA_GO_KR_KEY")
    if k:
        return k.strip()
    r = subprocess.run(["security", "find-generic-password", "-s", "data-go-kr-key", "-w"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    sys.exit("인증키가 없다. DATA_GO_KR_KEY 를 넣거나 키체인에 data-go-kr-key 를 두어라.")


def year(k, y):
    u = f"{API}?serviceKey={k}&solYear={y}&numOfRows=100&_type=json"
    with urllib.request.urlopen(u, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    body = d.get("response", {}).get("body") or {}
    item = (body.get("items") or {}).get("item")
    rows = item if isinstance(item, list) else ([item] if item else [])
    return [r for r in rows if r.get("isHoliday") == "Y"]


def main():
    k = urllib.parse.quote(key(), safe="")
    out, lo, hi = {}, None, None
    y = date.today().year - 2
    blank = 0
    while blank < 2 and y < date.today().year + 8:
        rows = year(k, y)
        if rows:
            blank = 0
            lo = y if lo is None else lo
            hi = y
            for r in rows:
                d = str(r["locdate"])
                out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = r["dateName"]
            print(f"  {y} {len(rows)}건", file=sys.stderr)
        else:
            blank += 1
            print(f"  {y} 없음", file=sys.stderr)
        y += 1

    if not out:
        sys.exit("한 건도 못 받았다. 키가 승인됐는지 확인하라.")
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "holidays.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"source": SOURCE, "from": lo, "to": hi,
                   "dates": dict(sorted(out.items()))},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"공휴일 {len(out)}일 · {lo}~{hi}년", file=sys.stderr)


if __name__ == "__main__":
    main()
