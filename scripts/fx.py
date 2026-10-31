"""발표일 환율 조회: market/fx.json (ECB 기준환율) 에서 그 날짜 또는 직전 영업일 값을 찾는다.

사용: python3 scripts/fx.py 2026-10-29 USD [금액]
  → 1 USD = 1,337.29원 (ECB 기준환율 2026-10-29)
  금액을 주면 원화 환산값도 출력. JPY는 100엔당 환율.
"""

import json
import sys

from lib import ROOT


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    day, cur = sys.argv[1], sys.argv[2].upper()
    data = json.loads((ROOT / "market" / "fx.json").read_text(encoding="utf-8"))
    days = [d for d in data["rates"] if d <= day and cur in data["rates"][d]]
    if not days:
        print(f"{day} 이전 {cur} 환율 없음")
        return 1
    d = max(days)
    rate = data["rates"][d][cur]
    unit = "100 JPY" if cur == "JPY" else f"1 {cur}"
    note = "" if d == day else f" (발표일이 휴일이라 직전 영업일 {d} 값)"
    print(f"{unit} = {rate:,.2f}원 (ECB 기준환율 {d}){note}")
    if len(sys.argv) > 3:
        amt = float(sys.argv[3].replace(",", ""))
        krw = amt * rate / (100 if cur == "JPY" else 1)
        print(f"{amt:,.0f} {cur} ≈ {krw:,.0f}원 ≈ {krw / 1e12:,.2f}조 원")
    return 0


if __name__ == "__main__":
    sys.exit(main())
