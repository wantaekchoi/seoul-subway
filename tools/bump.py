#!/usr/bin/env python3
"""확장 끝자리 버전을 올린다. 스토어가 같은 버전을 두 번 받지 않는다."""
import json

p = 'manifest.json'
m = json.load(open(p))
a, b, c = (list(map(int, m['version'].split('.'))) + [0, 0])[:3]
was, m['version'] = m['version'], f'{a}.{b}.{c + 1}'
with open(p, 'w', encoding='utf-8') as f:
    json.dump(m, f, ensure_ascii=False, indent=2)
    f.write('\n')
print(f'  버전 {was} → {m["version"]}')
