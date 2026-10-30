"""딜 노트·브리핑을 읽어 docs/ 에 정적 사이트를 만든다 (GitHub Pages가 docs/ 를 그대로 서비스).

docs/data.json 에 모든 데이터를 담고, site/ 의 html·css·js 를 복사한다.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timedelta, timezone

import markdown

from lib import (NAME_FIELDS, ROOT, alias_map, briefing_files, deal_files, load_deal, load_entities,
                 load_tags, split_front)

KST = timezone(timedelta(hours=9))
OUT = ROOT / "docs"


def render(md_text: str, aliases: dict) -> str:
    text = re.sub(r"<!--.*?-->", "", md_text, flags=re.S)
    text = text.replace("<", "&lt;")  # 원본에 섞인 HTML은 그대로 실행되지 않게

    def entity(m: re.Match) -> str:
        raw = m.group(1).strip()
        name = aliases.get(raw.lower(), raw)
        return f'<a class="ent" href="#/entity/{html.escape(name)}">{html.escape(raw)}</a>'

    text = re.sub(r"\[\[([^\]]+)\]\]", entity, text)
    out = markdown.markdown(text, extensions=["extra", "sane_lists"])
    # 딜 노트 링크(../deals/2026/x.md, ../2026/x.md)를 사이트 안 링크로
    out = re.sub(r'href="(?:\.\./)*(?:deals/)?\d{4}/([^"/]+)\.md"', r'href="#/deal/\1"', out)
    # 외부 링크는 새 탭
    out = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" target="_blank" rel="noopener"', out)
    return out


def main() -> None:
    tags = load_tags()
    entities = load_entities()
    aliases = alias_map(entities)

    deals = []
    for p in deal_files():
        m, body = load_deal(p)
        hist = body.split("## 진행 이력", 1)[-1].split("## ", 1)[0]
        hist_lines = re.findall(r"^- (\d{4}-\d{2}-\d{2}): (.+)$", hist, re.M)
        names = {f: [aliases.get(n.lower(), n) for n in m.get(f, [])] for f in NAME_FIELDS}
        summary = body.split("## 한 줄 요약", 1)[-1].split("## ", 1)[0]
        summary = re.sub(r"<!--.*?-->|\[\[|\]\]", "", summary, flags=re.S).strip()
        deals.append({
            "id": p.stem,
            "path": str(p.relative_to(ROOT)),
            "title": m.get("제목"),
            "status": m.get("상태"),
            "confidence": m.get("신뢰도"),
            "announced": m.get("발표일"),
            "updated": m.get("최종 업데이트"),
            "is_updated": len(hist_lines) > 1,  # 진행 이력이 2줄 이상 = 처음 등록 후 새 소식이 있었음
            "regions": m.get("지역", []),
            "crossborder": len(m.get("지역", [])) >= 2,
            "size": m.get("규모 구간"),
            "size_krw": m.get("규모(원화)"),
            "size_orig": m.get("규모(원 통화)"),
            "types": m.get("유형", []),
            "sectors": m.get("업종", []),
            "themes": m.get("테마", []),
            "names": names,
            "sources": m.get("출처", []),
            "summary": summary,
            "history": [{"date": d, "text": t} for d, t in hist_lines],
            "html": render(body, aliases),
        })
    deals.sort(key=lambda d: (d["updated"] or "", d["announced"] or ""), reverse=True)

    briefings = []
    for p in briefing_files():
        m, body = split_front(p.read_text(encoding="utf-8"))
        briefings.append({
            "date": str(m.get("날짜")),
            "alert": m.get("알림"),
            "new": m.get("신규", 0),
            "updated": m.get("업데이트", 0),
            "html": render(body, aliases),
        })
    briefings.sort(key=lambda b: b["date"], reverse=True)

    ents = {}
    for name, info in entities.items():
        info = info or {}
        ents[name] = {"type": info.get("type"), "country": info.get("country"),
                      "aliases": info.get("aliases", []) or []}

    data = {
        "built_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "axes": {
            "지역": list(tags["지역"].keys()),
            "규모 구간": tags["규모"],
            "유형": tags["유형"],
            "업종": tags["업종"],
            "테마": list(tags["테마"].keys()),
            "상태": tags["상태"],
        },
        "deals": deals,
        "briefings": briefings,
        "entities": ents,
    }

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site", OUT)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"사이트 생성: 딜 {len(deals)}건, 브리핑 {len(briefings)}건, 이름 {len(ents)}개 → docs/")


if __name__ == "__main__":
    main()
