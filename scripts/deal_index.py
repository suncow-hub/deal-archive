"""기존 딜 목록을 한 줄씩 출력한다. 에이전트가 중복·업데이트 여부를 판단할 때 쓴다.

사용: python3 scripts/deal_index.py [검색어]
"""

import sys

from lib import ROOT, deal_files, load_deal


def main() -> None:
    q = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    rows = []
    for p in deal_files():
        try:
            m, _ = load_deal(p)
        except Exception as e:  # noqa: BLE001
            rows.append(f"{p.relative_to(ROOT)} | 읽기 오류: {e}")
            continue
        parties = " / ".join(
            f"{k}:{','.join(m[k])}" for k in ("인수자", "대상", "매도자", "재무 자문", "법률 자문") if m[k]
        )
        line = (f"{p.relative_to(ROOT)} | {m.get('제목')} | {m.get('상태')} | 발표 {m.get('발표일')} | "
                f"업데이트 {m.get('최종 업데이트')} | {m.get('규모 구간')} | {parties}")
        if q in line.lower():
            rows.append(line)
    print(f"# 기존 딜 {len(rows)}건")
    print("\n".join(rows) if rows else "(없음)")


if __name__ == "__main__":
    main()
