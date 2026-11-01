"""[설정] 이슈 본문의 YAML을 검사해서 market/settings.yml 에 반영한다.

GitHub Actions(settings 워크플로)가 리포 주인이 연 이슈일 때만 실행한다.
- 본문은 환경 변수 BODY 로만 받는다 (셸 명령에 끼워 넣지 않음)
- 이슈 내용은 데이터로만 다룬다: 정해진 칸(strip/indices/stocks/exclude/tape)만 읽고, 형식이 다르면 거절
- 결과 메시지는 첫 번째 인자 파일에 쓴다 (이슈 댓글로 올라감)

사용: BODY="..." python scripts/apply_settings.py result.md
"""

from __future__ import annotations

import json
import os
import re
import sys

import yaml

from lib import (DEFAULT_SETTINGS, FX_CODES, ROOT, SETTINGS_PATH, dump_settings, load_entities, load_settings,
                 settings_errors, tracked_codes)

MAX_BODY = 20000


def krx_names() -> dict | None:
    p = ROOT / "market" / "krx_list.json"
    if not p.exists():
        return None
    return {c: n for c, n, *_ in json.loads(p.read_text(encoding="utf-8")).get("items", [])}


def parse(body: str) -> dict:
    if len(body) > MAX_BODY:
        raise ValueError("본문이 너무 김")
    m = re.search(r"```ya?ml\s*\n(.*?)\n```", body, re.S)
    if not m:
        raise ValueError("본문에 ```yaml ... ``` 블록이 없음")
    data = yaml.safe_load(m.group(1))
    if not isinstance(data, dict):
        raise ValueError("YAML이 '항목: 값' 형식이 아님")
    extra = set(data) - set(DEFAULT_SETTINGS)
    if extra:
        raise ValueError(f"모르는 항목: {', '.join(sorted(map(str, extra)))}")
    return data


def normalize(data: dict, names: dict | None) -> dict:
    cur = load_settings()
    s = {k: (data[k] if k in data else cur[k]) for k in DEFAULT_SETTINGS}
    s = {k: (v if v is not None else []) for k, v in s.items()}
    if not all(isinstance(v, list) for v in s.values()):
        return s   # settings_errors 가 잡는다
    code = lambda v: str(v).strip().upper().zfill(6) if re.fullmatch(r"\d{1,6}", str(v).strip()) else str(v).strip().upper()  # noqa: E731
    s["strip"] = list(dict.fromkeys(code(c) if not str(c).isalpha() else str(c).strip().upper() for c in s["strip"]))
    s["indices"] = list(dict.fromkeys(str(c).strip().upper() for c in s["indices"]))
    s["exclude"] = list(dict.fromkeys(code(c) for c in s["exclude"]))
    stocks, seen = [], set()
    for r in s["stocks"]:
        if not isinstance(r, dict):
            stocks.append(r)
            continue
        c = code(r.get("code", ""))
        if c in seen:
            continue
        seen.add(c)
        # 이름은 상장 목록의 공식 이름을 쓴다 (본문에 적힌 이름은 믿지 않음)
        stocks.append({"code": c, "name": (names or {}).get(c) or str(r.get("name", ""))[:30]})
    s["stocks"] = stocks
    tape, seen = [], set()
    for t in s["tape"]:
        if isinstance(t, dict) and str(t.get("symbol", "")).strip().upper() not in seen:
            sym = str(t.get("symbol", "")).strip().upper()
            seen.add(sym)
            tape.append({"symbol": sym, "title": str(t.get("title", "")).strip()})
        elif not isinstance(t, dict):
            tape.append(t)
    s["tape"] = tape
    return s


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.devnull
    body = os.environ.get("BODY", "")
    names = krx_names()
    before = load_settings()
    try:
        s = normalize(parse(body), names)
        errs = settings_errors(s, names)
        if not errs:
            tracked = tracked_codes(s, load_entities())
            for c in s["strip"]:
                if c not in s["indices"] and c not in FX_CODES and c not in tracked:
                    errs.append(f"strip: '{c}' 는 수집하는 지수나 추적 중인 종목이 아님")
    except (ValueError, yaml.YAMLError) as e:
        errs = [str(e)]
    if errs:
        msg = "설정을 적용하지 못했어요. 바뀐 것은 없습니다.\n\n" + "\n".join(f"- {e}" for e in errs[:20])
        open(out, "w", encoding="utf-8").write(msg)
        print(msg)
        return 1

    SETTINGS_PATH.write_text(dump_settings(s), encoding="utf-8")
    b_codes = {r["code"] for r in before["stocks"]}
    a_codes = {r["code"] for r in s["stocks"]}
    lines = ["설정을 적용했어요. 1~2분 뒤 사이트에 반영됩니다."]
    added = [f"{r['name']}({r['code']})" for r in s["stocks"] if r["code"] not in b_codes]
    removed = [f"{r['name']}({r['code']})" for r in before["stocks"] if r["code"] not in a_codes]
    if added:
        lines.append(f"- 종목 추가: {', '.join(added)} (1년치 시세를 함께 받음)")
    if removed:
        lines.append(f"- 종목 제외: {', '.join(removed)}")
    for k, label in (("strip", "위쪽 띠"), ("indices", "수집 지수"), ("exclude", "자동 추적 제외")):
        if s[k] != before[k]:
            lines.append(f"- {label}: {', '.join(map(str, s[k])) or '없음'}")
    if s["tape"] != before["tape"]:
        lines.append(f"- 해외 흐름띠: {', '.join(t['title'] for t in s['tape']) or '없음'}")
    if len(lines) == 1:
        lines.append("- 바뀐 항목은 없었어요.")
    msg = "\n".join(lines)
    open(out, "w", encoding="utf-8").write(msg)
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
