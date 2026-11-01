"""사명 변경 처리: 대표 이름을 새 이름으로 바꾸고, 옛 이름은 다른 표기(aliases)로 남긴다.
딜 노트(머리말 이름 칸, 본문 [[ ]]), rumors.yml 의 회사 이름도 한 번에 새 이름으로 바꾼다.
지난 브리핑은 그날의 기록이라 고치지 않는다.

사용: python3 scripts/rename_entity.py "옛 이름" "새 이름"
"""

from __future__ import annotations

import re
import sys

import yaml

from lib import ROOT, deal_files


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    old, new = sys.argv[1].strip(), sys.argv[2].strip()
    path = ROOT / "entities.yml"
    text = path.read_text(encoding="utf-8")
    ents = yaml.safe_load(text) or {}
    if old not in ents:
        print(f"'{old}' 은(는) entities.yml 대표 이름이 아님")
        return 1
    if new in ents:
        print(f"'{new}' 은(는) 이미 따로 등록돼 있음. 두 항목을 손으로 합친 뒤 다시 실행")
        return 1
    key = re.compile(rf'^({re.escape(old)}|"{re.escape(old)}"):\s*$', re.M)
    m = key.search(text)
    if not m:
        print("entities.yml 에서 항목 줄을 찾지 못함")
        return 1
    q = (lambda s: f'"{s}"') if re.search(r"[:#\[\]{},&*!|>'\"%@`]", new) else (lambda s: s)
    start = m.start()
    nxt = re.search(r"^\S", text[m.end():], re.M)
    end = m.end() + (nxt.start() if nxt else len(text) - m.end())
    block = text[start:end]
    block = key.sub(f"{q(new)}:", block, count=1)
    am = re.search(r"^  aliases: \[(.*)\]\s*$", block, re.M)
    if am:
        items = [a.strip() for a in am.group(1).split(",") if a.strip()]
        items = [x for x in items if x.strip('"') != new]
        items.insert(0, f'"{old}"')
        block = block[:am.start()] + f"  aliases: [{', '.join(items)}]" + block[am.end():]
    else:
        block = re.sub(r"^(\S.*:\s*\n)", rf'\1  aliases: ["{old}"]\n', block, count=1)
    text = text[:start] + block + text[end:]
    path.write_text(text, encoding="utf-8")

    changed = 0
    for p in deal_files():
        s = p.read_text(encoding="utf-8")
        s2 = s.replace(f"[[{old}]]", f"[[{new}]]").replace(f'"{old}"', f'"{new}"')
        if s2 != s:
            p.write_text(s2, encoding="utf-8")
            changed += 1
    rp = ROOT / "rumors.yml"
    if rp.exists():
        s = rp.read_text(encoding="utf-8")
        s2 = s.replace(f'"{old}"', f'"{new}"')
        if s2 != s:
            rp.write_text(s2, encoding="utf-8")
    print(f"'{old}' → '{new}': 회사 사전 변경, 딜 노트 {changed}건 이름 변경. python3 scripts/validate.py 로 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
