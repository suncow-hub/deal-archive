"""딜 노트·브리핑·사전 파일을 읽는 공용 함수."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

NAME_FIELDS = ["인수자", "대상", "매도자", "재무 자문", "법률 자문"]
LIST_FIELDS = ["지역", "유형", "업종", "테마", "출처"] + NAME_FIELDS
REQUIRED_FIELDS = ["제목", "상태", "신뢰도", "발표일", "최종 업데이트", "지역", "규모 구간",
                   "규모(원화)", "규모(원 통화)", "유형", "업종", "테마"] + NAME_FIELDS + ["출처"]
SECTIONS = ["한 줄 요약", "딜 구조", "밸류에이션", "왜 중요한가", "면접 포인트", "진행 이력", "관련 딜·뉴스"]


def split_front(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise ValueError("머리말(--- ... ---)이 없음")
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("머리말 형식 오류")
    return meta, m.group(2)


def as_list(v) -> list:
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


def load_tags() -> dict:
    return yaml.safe_load((ROOT / "tags.yml").read_text(encoding="utf-8"))


def load_entities() -> dict:
    data = yaml.safe_load((ROOT / "entities.yml").read_text(encoding="utf-8")) or {}
    return data


def alias_map(entities: dict) -> dict:
    m = {}
    for name, info in entities.items():
        m[name.lower()] = name
        for a in (info or {}).get("aliases", []) or []:
            m[str(a).lower()] = name
    return m


def deal_files() -> list[Path]:
    return sorted((ROOT / "deals").glob("*/*.md"))


def briefing_files() -> list[Path]:
    return sorted((ROOT / "briefings").glob("*.md"))


def load_deal(path: Path) -> tuple[dict, str]:
    meta, body = split_front(path.read_text(encoding="utf-8"))
    for f in LIST_FIELDS:
        meta[f] = [str(x) for x in as_list(meta.get(f))]
    for f in ("발표일", "최종 업데이트"):
        if meta.get(f) is not None:
            meta[f] = str(meta[f])
    return meta, body


def body_names(body: str) -> list[str]:
    return re.findall(r"\[\[([^\]]+)\]\]", body)


RUMOR_STATUSES = ["미확인", "사실로 확인", "부인", "소멸"]
RUMOR_CRED = ["낮음", "중간"]


def load_rumors() -> list:
    path = ROOT / "rumors.yml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ValueError("rumors.yml 은 목록(- 로 시작)이어야 함")
    return data


GLOSSARY_CATEGORIES = ["밸류에이션", "딜 구조", "자금 조달", "참여자·전략", "공시·규제", "거시경제"]


def load_glossary() -> list:
    path = ROOT / "glossary.yml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ValueError("glossary.yml 은 목록(- 로 시작)이어야 함")
    return data


# ---------------------------------------------------------------- 시세 설정 (market/settings.yml)
# 수집할 수 있는 국내 지수: 코드 → 공공데이터 지수명(idxNm)
INDEX_CATALOG = {
    "KOSPI": "코스피",
    "KOSDAQ": "코스닥",
    "KOSPI200": "코스피 200",
    "KOSDAQ150": "코스닥 150",
    "KRX300": "KRX 300",
}
FX_CODES = {"USDKRW": "원/달러"}   # 띠에 넣을 수 있는 환율 (ECB 기준환율)
SETTINGS_PATH = ROOT / "market" / "settings.yml"
SETTINGS_LIMITS = {"strip": 8, "stocks": 60, "exclude": 60, "tape": 12}
CODE_RE = re.compile(r"^[0-9A-Z]{6}$")
TV_RE = re.compile(r"^[A-Z0-9_]{1,20}:[A-Z0-9._!-]{1,30}$")

DEFAULT_SETTINGS = {
    "strip": ["KOSPI", "KOSDAQ", "USDKRW"],
    "indices": ["KOSPI", "KOSDAQ"],
    "stocks": [],
    "exclude": [],
    "tape": [
        {"symbol": "FOREXCOM:SPXUSD", "title": "S&P 500"}, {"symbol": "FOREXCOM:NSXUSD", "title": "나스닥 100"},
        {"symbol": "FOREXCOM:DJI", "title": "다우"}, {"symbol": "FX_IDC:USDKRW", "title": "원/달러"},
        {"symbol": "FRED:DGS10", "title": "미 10년물"}, {"symbol": "TVC:USOIL", "title": "WTI"},
        {"symbol": "TVC:GOLD", "title": "금"},
    ],
}


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_SETTINGS.items()}
    data = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("market/settings.yml 은 항목: 값 형식이어야 함")
    out = {k: data.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}
    for k in out:
        if out[k] is None:
            out[k] = []
    return out


def settings_errors(s: dict, krx_names: dict | None = None) -> list[str]:
    """설정 검사. krx_names({코드: 이름})가 있으면 종목코드가 실제 상장 종목인지도 본다."""
    err: list[str] = []
    for k in DEFAULT_SETTINGS:
        if not isinstance(s.get(k), list):
            err.append(f"{k}: 목록이어야 함")
    if err:
        return err
    for k, n in SETTINGS_LIMITS.items():
        if len(s[k]) > n:
            err.append(f"{k}: 최대 {n}개 (지금 {len(s[k])}개)")
    for c in s["indices"]:
        if c not in INDEX_CATALOG:
            err.append(f"indices: '{c}' 는 지원하지 않는 지수 (가능: {', '.join(INDEX_CATALOG)})")
    codes = set()
    for row in s["stocks"]:
        code = str((row or {}).get("code", "")) if isinstance(row, dict) else ""
        if not CODE_RE.match(code):
            err.append(f"stocks: 종목코드 '{code}' 는 6자리 문자열이어야 함 (따옴표로 감싸기)")
            continue
        if krx_names is not None and code not in krx_names:
            err.append(f"stocks: '{code}' 는 상장 종목 목록에 없음")
        codes.add(code)
    for c in s["exclude"]:
        if not CODE_RE.match(str(c)):
            err.append(f"exclude: '{c}' 는 6자리 문자열이어야 함")
    for c in s["strip"]:
        c = str(c)
        if not (c in s["indices"] or c in FX_CODES or CODE_RE.match(c)):
            err.append(f"strip: '{c}' 는 수집 중인 지수·환율(USDKRW)·종목코드 중 하나여야 함")
    for t in s["tape"]:
        if not isinstance(t, dict) or not TV_RE.match(str(t.get("symbol", ""))):
            err.append(f"tape: '{(t or {}).get('symbol') if isinstance(t, dict) else t}' 는 '거래소:티커' 형식이어야 함")
        elif not str(t.get("title", "")).strip() or len(str(t["title"])) > 20:
            err.append(f"tape: {t['symbol']} 이름은 1~20자")
    return err


def tracked_codes(s: dict, entities: dict) -> dict:
    """추적할 종목 {코드: 이름}: 설정의 stocks + 회사 사전의 krx 코드 - exclude"""
    out = {str(r["code"]): str(r.get("name", "")) for r in s["stocks"]}
    for name, info in entities.items():
        code = str((info or {}).get("krx") or "").strip()
        if code:
            out.setdefault(code.zfill(6), name)
    for c in s["exclude"]:
        out.pop(str(c), None)
    return out


def dump_settings(s: dict) -> str:
    """사람이 읽기 좋은 settings.yml 텍스트"""
    q = lambda v: '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'  # noqa: E731
    lines = [
        "# 시세 설정 — 사이트 차트 탭의 '편집'에서 바꾸면 자동으로 고쳐진다 (리포 주인만 적용됨)",
        "# strip: 첫 화면 위쪽 띠에 보일 항목 (지수 코드, USDKRW, 종목코드)",
        "# indices: 수집할 국내 지수 (" + ", ".join(f"{k}={v}" for k, v in INDEX_CATALOG.items()) + ")",
        "# stocks: 직접 추가한 관심 종목. 딜 아카이브에 나온 상장사(entities.yml의 krx)는 자동으로 추적된다",
        "# exclude: 자동 추적 종목 중 빼고 싶은 종목코드",
        "# tape: 첫 화면 해외 시세 흐름띠 (TradingView 기호)",
        "strip: [" + ", ".join(q(c) for c in s["strip"]) + "]",
        "indices: [" + ", ".join(q(c) for c in s["indices"]) + "]",
        "stocks:" + ("" if s["stocks"] else " []"),
        *[f"  - {{code: {q(r['code'])}, name: {q(r.get('name', ''))}}}" for r in s["stocks"]],
        "exclude: [" + ", ".join(q(c) for c in s["exclude"]) + "]",
        "tape:" + ("" if s["tape"] else " []"),
        *[f"  - {{symbol: {q(t['symbol'])}, title: {q(t['title'])}}}" for t in s["tape"]],
    ]
    return "\n".join(lines) + "\n"


def fx_summary() -> dict:
    """market/fx.json 에서 원/달러 최신값과 전일 대비"""
    p = ROOT / "market" / "fx.json"
    if not p.exists():
        return {}
    rates = json.loads(p.read_text(encoding="utf-8")).get("rates", {})
    days = sorted(d for d in rates if (rates[d] or {}).get("USD"))
    if not days:
        return {}
    cur = rates[days[-1]]["USD"]
    prev = rates[days[-2]]["USD"] if len(days) > 1 else None
    return {"date": days[-1], "USD": cur, "USD_change_pct": round((cur / prev - 1) * 100, 2) if prev else None}
