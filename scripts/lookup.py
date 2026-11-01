"""에이전트용 찾아보기 도구. 딜 목록·회사 사전·용어집을 통째로 읽지 않고 필요한 것만 찾는다.
(쌓일수록 통째로 읽으면 토큰이 늘고, 긴 목록에서는 모델이 오히려 놓치기 쉬워서)

  딜 찾기 (세 묶음을 합쳐 한 줄씩 출력):
    python3 scripts/lookup.py deals --names "DoorDash" "인스타카트" --sectors "IT·소프트웨어·플랫폼" --themes "AI·데이터센터" [--recent 60] [--sector-days 365]
      ① 이름: 회사 사전의 다른 표기까지 모두 넓혀 아카이브 전체에서 찾기 (기간 제한 없음)
      ② 같은 업종·테마: 최근 --sector-days 일 (기본 365)
      ③ 최근 목록: 최근 --recent 일 (기본 60) 의 모든 딜
  회사 찾기:   python3 scripts/lookup.py entity "SK Inc." "헝다"      (대표 이름·다른 표기 일치 → 없으면 이름 일부가 겹치는 후보)
  코드로 찾기: python3 scripts/lookup.py code 005930 "NASDAQ:DASH"   (사명이 바뀌어도 종목코드는 그대로인 경우가 많다)
  용어 찾기:   python3 scripts/lookup.py term "언아웃" "go-shop"
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone

import yaml

from lib import NAME_FIELDS, ROOT, deal_files, load_deal, load_entities, load_glossary

TODAY = datetime.now(timezone(timedelta(hours=9))).date()
norm = lambda s: re.sub(r"[\s·.,()㈜&'-]", "", str(s)).lower()  # noqa: E731
# 이름 일부로 찾을 때 무시하는 흔한 단어 (이것만 겹치면 같은 회사 후보로 보지 않음)
GENERIC = {norm(w) for w in ["group", "holdings", "holding", "inc", "corp", "corporation", "co", "ltd", "limited", "plc",
                             "capital", "partners", "management", "global", "securities", "bank", "the", "company",
                             "그룹", "홀딩스", "지주", "파트너스", "캐피탈", "증권", "은행"]}


def alias_groups(ents: dict) -> dict[str, set[str]]:
    """{정규화된 아무 표기: {대표 이름}}"""
    out: dict[str, set[str]] = {}
    for name, info in ents.items():
        for a in [name] + list((info or {}).get("aliases") or []):
            out.setdefault(norm(a), set()).add(name)
    return out


def expand(names: list[str], ents: dict) -> set[str]:
    """입력 이름 → 대표 이름 + 모든 다른 표기 (정규화)"""
    groups = alias_groups(ents)
    keys = set()
    for n in names:
        keys.add(norm(n))
        for canon in groups.get(norm(n), set()):
            keys.add(norm(canon))
            keys |= {norm(a) for a in (ents[canon] or {}).get("aliases") or []}
    return {k for k in keys if k}


def deal_line(p, m) -> str:
    parties = " / ".join(f"{f}:{','.join(m[f])}" for f in NAME_FIELDS if m.get(f))
    tags = ",".join(m.get("업종", []) + m.get("테마", []))
    return (f"{p.relative_to(ROOT)} | {m.get('제목')} | {m.get('상태')} | 발표 {m.get('발표일')} | "
            f"업데이트 {m.get('최종 업데이트')} | {m.get('규모 구간')} | {tags} | {parties}")


def days_ago(d: str) -> int:
    try:
        return (TODAY - datetime.strptime(str(d), "%Y-%m-%d").date()).days
    except ValueError:
        return 10**6


def cmd_deals(a) -> None:
    ents = load_entities()
    keys = expand(a.names or [], ents)
    by_name, by_tag, recent = [], [], []
    for p in deal_files():
        m, body = load_deal(p)
        line = deal_line(p, m)
        names = [n for f in NAME_FIELDS for n in m.get(f, [])] + re.findall(r"\[\[([^\]]+)\]\]", body)
        hay = {norm(n) for n in names} | {norm(m.get("제목", ""))}
        title = norm(m.get("제목", ""))
        if keys and (keys & hay or any(len(k) >= 3 and k in title for k in keys)):
            by_name.append(line)
            continue
        age = min(days_ago(m.get("최종 업데이트")), days_ago(m.get("발표일")))
        if age <= a.sector_days and (set(a.sectors or []) & set(m.get("업종", [])) or set(a.themes or []) & set(m.get("테마", []))):
            by_tag.append(line)
            continue
        if age <= a.recent:
            recent.append(line)
    print(f"# ① 이름·다른 표기로 찾은 딜 {len(by_name)}건 (전체 기간)")
    print("\n".join(by_name) or "(없음)")
    print(f"\n# ② 같은 업종·테마 딜 {len(by_tag)}건 (최근 {a.sector_days}일)")
    print("\n".join(by_tag) or "(없음)")
    print(f"\n# ③ 그 밖의 최근 딜 {len(recent)}건 (최근 {a.recent}일)")
    print("\n".join(recent) or "(없음)")
    print(f"\n# 아카이브 전체 {len(deal_files())}건 중 위 {len(by_name) + len(by_tag) + len(recent)}건만 표시")


def show(name: str, info: dict) -> str:
    keep = {k: v for k, v in (info or {}).items() if k != "profile"}
    prof = (info or {}).get("profile") or {}
    if prof.get("owner"):
        keep["owner(profile)"] = prof["owner"]
    if prof.get("as_of"):
        keep["profile_as_of"] = prof["as_of"]
    return yaml.safe_dump({name: keep}, allow_unicode=True, sort_keys=False).rstrip()


def cmd_entity(a) -> None:
    ents = load_entities()
    groups = alias_groups(ents)
    for q in a.names:
        hit = groups.get(norm(q))
        if hit:
            print(f"# '{q}' → 등록됨")
            for c in sorted(hit):
                print(show(c, ents[c]))
            continue
        nq = norm(q)
        parts = [w for w in re.split(r"[\s·,()]+", str(q)) if len(norm(w)) >= 2 and norm(w) not in GENERIC]
        cand = []
        for name, info in ents.items():
            alls = [name] + list((info or {}).get("aliases") or [])
            if any(nq and (nq in norm(x) or norm(x) in nq) for x in alls if len(norm(x)) >= 2) or \
               any(norm(w) in norm(x) for w in parts for x in alls if len(norm(w)) >= 3):
                cand.append(name)
        print(f"# '{q}' → 등록 안 됨. 이름 일부가 겹치는 후보 {len(cand)}개" + (" (같은 회사인지 확인)" if cand else ""))
        for c in cand[:8]:
            print(show(c, ents[c]))
    print("\n# 같은 회사가 아니면 새로 등록. 같은 회사인데 사명이 바뀐 것이면: python3 scripts/rename_entity.py \"옛 이름\" \"새 이름\"")


def cmd_code(a) -> None:
    ents = load_entities()
    for q in a.codes:
        hit = [n for n, i in ents.items() if str((i or {}).get("krx") or "") == q.strip()
               or str((i or {}).get("ticker") or "").upper() == q.strip().upper()
               or (":" not in q and str((i or {}).get("ticker") or "").upper().endswith(":" + q.strip().upper()))]
        print(f"# 코드 '{q}' → {len(hit)}개")
        for n in hit:
            print(show(n, ents[n]))


def cmd_term(a) -> None:
    gl = load_glossary()
    for q in a.words:
        nq = norm(q)
        exact, part = [], []
        for g in gl:
            alls = [g.get("term"), g.get("en")] + list(g.get("match") or []) + list(g.get("aliases") or [])
            alls = [norm(x) for x in alls if x]
            if nq in alls:
                exact.append(g)
            elif len(nq) >= 2 and any(nq in x or (len(x) >= 2 and x in nq) for x in alls):
                part.append(g)
        print(f"# '{q}' → " + ("있음" if exact else f"없음 (비슷한 항목 {len(part)}개)"))
        for g in (exact or part)[:5]:
            print(f"- {g.get('id')}: {g.get('term')} ({g.get('en') or ''}) — {g.get('short')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("deals")
    d.add_argument("--names", nargs="*")
    d.add_argument("--sectors", nargs="*")
    d.add_argument("--themes", nargs="*")
    d.add_argument("--recent", type=int, default=60)
    d.add_argument("--sector-days", type=int, default=365)
    e = sub.add_parser("entity")
    e.add_argument("names", nargs="+")
    c = sub.add_parser("code")
    c.add_argument("codes", nargs="+")
    t = sub.add_parser("term")
    t.add_argument("words", nargs="+")
    a = ap.parse_args()
    {"deals": cmd_deals, "entity": cmd_entity, "code": cmd_code, "term": cmd_term}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
