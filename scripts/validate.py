"""딜 노트·브리핑·사전 파일 검사. 문제가 있으면 목록을 출력하고 종료 코드 1."""

import re
import sys

import yaml

from lib import (GLOSSARY_CATEGORIES, NAME_FIELDS, REQUIRED_FIELDS, ROOT, RUMOR_CRED, RUMOR_STATUSES, SECTIONS,
                 body_names, briefing_files, deal_files, load_deal, load_entities, load_glossary, load_rumors,
                 load_settings, load_tags, settings_errors, split_front)

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ENTITY_TYPES = {"기업", "PE·VC", "재무 자문사", "법률 자문사", "정부·기관"}


def main() -> int:
    errors: list[str] = []
    tags = load_tags()
    regions = set(tags["지역"])
    sizes = set(tags["규모"])
    types = set(tags["유형"])
    statuses = set(tags["상태"])
    sectors = set(tags["업종"])
    themes = set(tags["테마"])

    try:
        entities = load_entities()
    except yaml.YAMLError as e:
        print(f"entities.yml: YAML 오류 {e}")
        return 1
    for name, info in entities.items():
        info = info or {}
        if info.get("type") not in ENTITY_TYPES:
            errors.append(f"entities.yml: {name} type '{info.get('type')}' 은(는) {sorted(ENTITY_TYPES)} 중 하나여야 함")
        if info.get("country") and info["country"] not in regions:
            errors.append(f"entities.yml: {name} country '{info['country']}' 이(가) tags.yml 지역에 없음")

    for p in deal_files():
        rel = p.relative_to(ROOT)
        if not re.match(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$", p.name):
            errors.append(f"{rel}: 파일 이름은 YYYY-MM-DD-영문-slug.md")
        try:
            m, body = load_deal(p)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{rel}: {e}")
            continue
        for f in REQUIRED_FIELDS:
            if f not in m:
                errors.append(f"{rel}: 머리말에 '{f}' 없음")
        if not m.get("제목"):
            errors.append(f"{rel}: 제목 비어 있음")
        for f in ("발표일", "최종 업데이트"):
            if not DATE.match(str(m.get(f) or "")):
                errors.append(f"{rel}: {f} 형식은 YYYY-MM-DD")
        checks = [("상태", statuses, False), ("규모 구간", sizes, False), ("지역", regions, True),
                  ("유형", types, True), ("업종", sectors, True), ("테마", themes, True)]
        for field, allowed, many in checks:
            vals = m.get(field) if many else [m.get(field)]
            for v in vals:
                if str(v) not in allowed:
                    errors.append(f"{rel}: {field} '{v}' 은(는) tags.yml에 없는 값")
        if not m.get("지역"):
            errors.append(f"{rel}: 지역이 비어 있음")
        if m.get("신뢰도") not in ("공시 확정", "보도 기준"):
            errors.append(f"{rel}: 신뢰도는 '공시 확정' 또는 '보도 기준'")
        names = [n for f in NAME_FIELDS for n in m.get(f, [])] + body_names(body)
        for n in sorted(set(names)):
            if n not in entities:
                errors.append(f"{rel}: 이름 '{n}' 이(가) entities.yml에 없음 (대표 이름으로 쓰거나 등록)")
        heads = re.findall(r"^## (.+?)\s*$", body, re.M)
        if heads != SECTIONS:
            errors.append(f"{rel}: 섹션 구성이 템플릿과 다름 → {heads}")
        hist = body.split("## 진행 이력", 1)[-1].split("## ", 1)[0]
        if not re.search(r"^- \d{4}-\d{2}-\d{2}: \S", hist, re.M):
            errors.append(f"{rel}: 진행 이력에 날짜 줄이 없음")

    for p in briefing_files():
        rel = p.relative_to(ROOT)
        try:
            m, _ = split_front(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{rel}: {e}")
            continue
        if str(m.get("날짜")) != p.stem:
            errors.append(f"{rel}: 날짜가 파일 이름과 다름")
        if not m.get("알림") or len(str(m["알림"])) > 60:
            errors.append(f"{rel}: 알림은 1~60자")

    try:
        rumors = load_rumors()
    except Exception as e:  # noqa: BLE001
        rumors = []
        errors.append(f"rumors.yml: {e}")
    deal_ids = {p.stem for p in deal_files()}
    seen_ids = set()
    for i, r in enumerate(rumors):
        tag = f"rumors.yml[{i}]"
        if not isinstance(r, dict):
            errors.append(f"{tag}: 항목 형식 오류")
            continue
        rid = str(r.get("id") or "")
        tag = f"rumors.yml:{rid or i}"
        if not re.match(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$", rid):
            errors.append(f"{tag}: id는 YYYY-MM-DD-영문-slug")
        if rid in seen_ids:
            errors.append(f"{tag}: id 중복")
        seen_ids.add(rid)
        for f in ("first_seen", "last_seen"):
            if not DATE.match(str(r.get(f) or "")):
                errors.append(f"{tag}: {f} 형식은 YYYY-MM-DD")
        for f in ("title", "claim"):
            if not r.get(f):
                errors.append(f"{tag}: {f} 비어 있음")
        if r.get("status") not in RUMOR_STATUSES:
            errors.append(f"{tag}: status는 {RUMOR_STATUSES} 중 하나")
        if r.get("status") == "사실로 확인" and r.get("deal") not in deal_ids:
            errors.append(f"{tag}: 사실로 확인이면 deal에 있는 딜 노트 id를 적어야 함")
        srcs = r.get("sources") or []
        if not srcs:
            errors.append(f"{tag}: sources 비어 있음")
        for s in srcs:
            if not isinstance(s, dict) or not s.get("name") or s.get("credibility") not in RUMOR_CRED:
                errors.append(f"{tag}: sources 항목은 name과 credibility({'/'.join(RUMOR_CRED)}) 필요")

    try:
        glossary = load_glossary()
    except Exception as e:  # noqa: BLE001
        glossary = []
        errors.append(f"glossary.yml: {e}")
    terms = {str(g.get("term")) for g in glossary if isinstance(g, dict)}
    gids = set()
    for i, g in enumerate(glossary):
        if not isinstance(g, dict):
            errors.append(f"glossary.yml[{i}]: 항목 형식 오류")
            continue
        tag = f"glossary.yml:{g.get('id') or i}"
        gid = str(g.get("id") or "")
        if not re.match(r"^[a-z0-9-]+$", gid):
            errors.append(f"{tag}: id는 영문 소문자·숫자·하이픈")
        if gid in gids:
            errors.append(f"{tag}: id 중복")
        gids.add(gid)
        for f in ("term", "short", "category"):
            if not g.get(f):
                errors.append(f"{tag}: {f} 비어 있음")
        if g.get("category") and g["category"] not in GLOSSARY_CATEGORIES:
            errors.append(f"{tag}: category는 {GLOSSARY_CATEGORIES} 중 하나")
        for f in ("match", "aliases", "related"):
            if g.get(f) is not None and not isinstance(g.get(f), list):
                errors.append(f"{tag}: {f}는 목록 [..] 이어야 함")
        if g.get("deal") and g["deal"] not in deal_ids:
            errors.append(f"{tag}: deal '{g['deal']}' 딜 노트가 없음")
        for r in g.get("related") or []:
            if r not in terms:
                errors.append(f"{tag}: related '{r}' 이(가) 용어집 term에 없음")

    try:
        for e in settings_errors(load_settings()):
            errors.append(f"market/settings.yml: {e}")
    except (ValueError, yaml.YAMLError) as e:
        errors.append(f"market/settings.yml: {e}")
    for name, info in entities.items():
        k = str((info or {}).get("krx") or "")
        if k and not re.fullmatch(r"[0-9A-Z]{6}", k):
            errors.append(f"entities.yml: {name} krx '{k}' 는 6자리 문자열")

    if errors:
        print(f"검사 실패 {len(errors)}건")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    print(f"검사 통과: 딜 {len(deal_files())}건, 브리핑 {len(briefing_files())}건, 이름 {len(entities)}개, 소문 {len(rumors)}건, 용어 {len(glossary)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
