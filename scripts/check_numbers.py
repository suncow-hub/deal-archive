"""딜 노트 계산 검사 (AI 없이, 비용 0).

글로 적힌 숫자끼리 서로 맞는지 기계적으로 확인한다. 틀린 '사실'을 잡는 게 아니라
환산·옮겨 적기·날짜 같은 실수를 잡는다. 문제가 있으면 목록을 출력한다 (사이트 빌드는 막지 않음).

- 원화 환산: 규모(원 통화)의 외화 금액 × 발표일 ECB 환율 ≈ 규모(원화) 첫 금액 (오차 3% 이내)
- 규모 구간 태그가 원화 금액과 맞는지
- 비교 숫자(배수·프리미엄)가 말이 되는 범위인지, 기업가치·지분가치 원화 숫자가 규모와 크게 어긋나지 않는지
- 날짜: 최종 업데이트 ≥ 발표일, 진행 이력 날짜 순서, 오늘 이후 날짜 없음

사용: python3 scripts/check_numbers.py [--json work/number_check.json]
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone

from lib import COMPARE_NUM_FIELDS, ROOT, deal_files, fx_rate, load_deal

TODAY = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
CURS = ["USD", "EUR", "JPY", "CNY", "HKD", "GBP", "SGD"]
BUCKETS = [("1천억 미만", 0, 1e3), ("1천억~5천억", 1e3, 5e3), ("5천억~1조", 5e3, 1e4),
           ("1조~5조", 1e4, 5e4), ("5조~20조", 5e4, 2e5), ("20조 이상", 2e5, 1e12)]  # 단위: 억원


def krw_eok(text: str) -> float | None:
    """'약 1조 3105억 원', '약 6,854억 원', '약 22.7조 원' → 억원 숫자 (첫 금액)"""
    t = str(text or "").replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*조(?:\s*(\d+)\s*억)?|(\d+(?:\.\d+)?)\s*억", t)
    if not m:
        return None
    if m.group(1):
        return float(m.group(1)) * 1e4 + (float(m.group(2)) if m.group(2) else 0)
    return float(m.group(3))


def foreign(text: str) -> tuple[str, float] | None:
    """'USD 약 4.0B', 'EUR 11.18B', 'HKD 4.03B', 'USD 513.7M' → (통화, 금액)"""
    m = re.search(r"\b(" + "|".join(CURS) + r")\s*(?:약\s*)?(\d+(?:\.\d+)?)\s*([BM])\b", str(text or ""))
    if not m:
        return None
    return m.group(1), float(m.group(2)) * (1e9 if m.group(3) == "B" else 1e6)


def check(path) -> list[str]:
    out = []
    meta, body = load_deal(path)
    ann = str(meta.get("발표일") or "")
    won = krw_eok(meta.get("규모(원화)"))
    fx = foreign(meta.get("규모(원 통화)"))
    if fx and won and ann:
        r = fx_rate(ann, fx[0])
        if r:
            rate, d = r
            expect = fx[1] * rate / (100 if fx[0] == "JPY" else 1) / 1e8
            diff = abs(won - expect) / expect
            if diff > 0.03:
                out.append(f"원화 환산: {fx[0]} {fx[1] / 1e9:g}B × 발표일 환율 {rate:,.2f}원({d}) = 약 {expect:,.0f}억 원인데 "
                           f"노트는 {won:,.0f}억 원 ({diff:.0%} 차이)")
    if "미확인" in str(meta.get("규모(원 통화)")) and "환율" in str(meta.get("규모(원 통화)")):
        out.append("원화 환산: 발표일 환율이 '미확인'으로 남아 있음 → scripts/fx.py 로 발표일 환율을 넣을 것")
    size = meta.get("규모 구간")
    if won and size and size != "비공개":
        right = next((n for n, lo, hi in BUCKETS if lo <= won < hi), None)
        if right and right != size:
            out.append(f"규모 구간: 원화 {won:,.0f}억 원이면 '{right}'인데 '{size}'로 돼 있음")

    comp = meta.get("비교") or {}
    if isinstance(comp, dict):
        for f, lo, hi in (("EV/EBITDA", 0, 200), ("EV/매출", 0, 100), ("P/E", 0, 500), ("프리미엄(%)", -95, 300)):
            v = comp.get(f)
            if isinstance(v, (int, float)) and not lo < v < hi:
                out.append(f"비교 숫자: {f} {v} 는 흔치 않은 값 (확인 필요)")
        for f in ("기업가치(억원)", "지분가치(억원)"):
            v = comp.get(f)
            if isinstance(v, (int, float)) and won and not (won / 20 <= v <= won * 20):
                out.append(f"비교 숫자: {f} {v:,.0f} 이(가) 규모(원화) {won:,.0f}억 원과 20배 넘게 차이남 (단위 확인)")
        for f in COMPARE_NUM_FIELDS:
            if comp.get(f) is not None and not isinstance(comp.get(f), (int, float)):
                out.append(f"비교 숫자: {f} 는 숫자만 (지금 '{comp.get(f)}')")

    upd = str(meta.get("최종 업데이트") or "")
    if ann and upd and upd < ann:
        out.append(f"날짜: 최종 업데이트({upd})가 발표일({ann})보다 앞섬")
    hist = re.findall(r"^- (\d{4}-\d{2}-\d{2}):", body.split("## 진행 이력", 1)[-1].split("\n## ", 1)[0], re.M)
    if hist != sorted(hist):
        out.append("날짜: 진행 이력이 날짜순이 아님")
    for d in hist + [ann, upd]:
        if d and d > TODAY:
            out.append(f"날짜: {d} 는 오늘({TODAY}) 이후 날짜인데 이력·발표일에 들어 있음")
    if hist and upd and hist[-1] > upd:
        out.append(f"날짜: 마지막 진행 이력({hist[-1]})이 최종 업데이트({upd})보다 늦음")
    return out


def main() -> int:
    args = sys.argv[1:]
    result = {}
    for p in deal_files():
        try:
            issues = check(p)
        except Exception as e:  # noqa: BLE001
            issues = [f"읽기 오류: {e}"]
        if issues:
            result[str(p.relative_to(ROOT))] = issues
    if "--json" in args:
        out = ROOT / args[args.index("--json") + 1]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if not result:
        print(f"계산 검사 통과: 딜 {len(deal_files())}건")
    else:
        print(f"계산 검사: 확인 필요 {sum(map(len, result.values()))}건")
        for k, v in result.items():
            print(f"- {k}")
            for i in v:
                print(f"    {i}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
