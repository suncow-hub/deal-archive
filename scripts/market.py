"""한국 시세 수집: 금융위원회 공공데이터 API로 국내 지수와 관심 종목의 일별 시세를 쌓는다.

- 무엇을 모을지는 market/settings.yml (사이트 차트 탭 '편집'에서 바꿈)
- 관심 종목 = settings.yml 의 stocks + entities.yml 에서 krx 코드가 있는 회사 - exclude
- 종목마다 market/kr/<코드>.json, 지수는 market/kr/<지수코드>.json (예: KOSPI.json)
- 처음 보는 종목은 1년치를 한 번에 받고, 이후엔 새 날짜만 덧붙인다
- market/krx_list.json: 전체 상장 종목 이름·코드 (편집 화면의 종목 검색용, 일주일에 한 번 갱신)
- market/summary.json: 지수 띠용 최신 값, market/status.json: 실행 결과 (키는 남기지 않음)
- 데이터는 기준일 다음 영업일 오후 1시 이후 제공된다 (공공데이터포털 안내)
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from lib import INDEX_CATALOG, fx_summary, load_entities, load_settings, tracked_codes

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "market" / "kr"
KST = timezone(timedelta(hours=9))
UA = "deal-archive/1.0 (personal study project; https://github.com/suncow-hub/deal-archive)"
KEY = os.environ.get("DATA_GO_KR_KEY", "")

# 서비스 주소는 V2를 먼저 쓰고, 안 되면 예전 주소로
INDEX_URLS = [
    "https://apis.data.go.kr/1160100/GetMarketIndexInfoService_V2/getStockMarketIndex_V2",
    "https://apis.data.go.kr/1160100/service/GetMarketIndexInfoService/getStockMarketIndex",
]
STOCK_URLS = [
    "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2",
    "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo",
]


def scrub(s: str) -> str:
    s = str(s)
    if KEY:
        s = s.replace(KEY, "***").replace(requests.utils.quote(KEY, safe=""), "***")
    return re.sub(r"(serviceKey=)[^&\s]+", r"\1***", s)


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def call(urls: list[str], params: dict, status: dict) -> list[dict]:
    return call_full(urls, params, status)[0]


def call_full(urls: list[str], params: dict, status: dict) -> tuple[list[dict], int]:
    """여러 주소를 차례로 시도. 성공한 주소는 기억해서 다음부터 먼저 쓴다. (항목, 전체 개수)"""
    last = None
    params = dict(params)
    kind = params.pop("_kind", "")
    for url in urls:
        try:
            r = requests.get(url, params={"serviceKey": KEY, "resultType": "json", **params},
                             headers={"User-Agent": UA}, timeout=30)
            text = r.text
            if r.status_code != 200 or not text.strip().startswith("{"):
                last = f"HTTP {r.status_code}: {scrub(text[:160])}"
                continue
            data = json.loads(text)
            header = data.get("response", {}).get("header", {})
            if header.get("resultCode") not in ("00", "0", None):
                last = f"{header.get('resultCode')} {header.get('resultMsg')}"
                continue
            body = data.get("response", {}).get("body", {})
            items = (body.get("items") or {}).get("item") or []
            if isinstance(items, dict):
                items = [items]
            if url != urls[0]:
                urls.remove(url)
                urls.insert(0, url)
            status.setdefault("endpoints", {})[kind] = url.split("/1160100/")[-1]
            return items, int(body.get("totalCount") or len(items))
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {scrub(e)}"
    raise RuntimeError(last or "알 수 없는 오류")


def load_series(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def merge(path: Path, meta: dict, rows: list[list]) -> int:
    data = load_series(path)
    have = {r[0]: r for r in data.get("series", [])}
    before = len(have)
    for r in rows:
        have[r[0]] = r
    series = [have[d] for d in sorted(have)]
    cutoff = (datetime.now(KST) - timedelta(days=366 * 3)).strftime("%Y-%m-%d")
    series = [r for r in series if r[0] >= cutoff]  # 최대 3년 보관
    data.update(meta)
    data["series"] = series
    data["fields"] = ["date", "open", "high", "low", "close", "volume"]
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(have) - before


def start_date(path: Path) -> str:
    data = load_series(path)
    if data.get("series"):
        last = datetime.strptime(data["series"][-1][0], "%Y-%m-%d")
        return (last + timedelta(days=1)).strftime("%Y%m%d")
    return (datetime.now(KST) - timedelta(days=366)).strftime("%Y%m%d")


def iso(basdt: str) -> str:
    return f"{basdt[:4]}-{basdt[4:6]}-{basdt[6:8]}"


def fetch_index(code: str, name: str, status: dict) -> None:
    path = OUT / f"{code}.json"
    begin = start_date(path)
    end = datetime.now(KST).strftime("%Y%m%d")
    if begin > end:
        status["items"][code] = "최신"
        return
    norm = lambda x: re.sub(r"\s+", "", str(x or ""))  # noqa: E731  ("코스피 200" / "코스피200" 둘 다 맞게)
    base = {"beginBasDt": begin, "endBasDt": end, "numOfRows": 1000, "pageNo": 1, "_kind": "index"}
    items = [it for it in call(INDEX_URLS, {"idxNm": name, **base}, status) if norm(it.get("idxNm")) == norm(name)]
    if not items:
        # 이름 표기가 다를 때: 최근 열흘치를 '비슷한 이름'으로 찾아 정확한 지수명을 알아낸 뒤 다시 받는다
        recent = (datetime.now(KST) - timedelta(days=10)).strftime("%Y%m%d")
        cands = call(INDEX_URLS, {**base, "likeIdxNm": name.split()[0], "beginBasDt": recent, "numOfRows": 1000}, status)
        exact = next((it.get("idxNm") for it in cands if norm(it.get("idxNm")) == norm(name)), None)
        if exact and exact != name:
            items = [it for it in call(INDEX_URLS, {"idxNm": exact, **base}, status) if it.get("idxNm") == exact]
    if not items and not load_series(path):
        status["items"][code] = f"데이터 없음 (지수명 '{name}' 확인 필요)"
        return
    rows = [[iso(it["basDt"]), num(it.get("mkp")), num(it.get("hipr")), num(it.get("lopr")),
             num(it.get("clpr")), num(it.get("trqu"))]
            for it in items if it.get("basDt")]
    added = merge(path, {"code": code, "name": name, "kind": "index"}, rows)
    status["items"][code] = f"{added}일 추가"


def fetch_stock(code: str, hint: str, status: dict) -> None:
    path = OUT / f"{code}.json"
    begin = start_date(path)
    end = datetime.now(KST).strftime("%Y%m%d")
    if begin > end:
        status["items"][code] = "최신"
        return
    items = call(STOCK_URLS, {"likeSrtnCd": code, "beginBasDt": begin, "endBasDt": end, "numOfRows": 1000,
                              "pageNo": 1, "_kind": "stock"}, status)
    mine = [it for it in items if str(it.get("srtnCd", "")).lstrip("A") == code]
    if not mine and not load_series(path):
        status["items"][code] = f"데이터 없음 (코드 확인 필요: {hint})"
        return
    rows = [[iso(it["basDt"]), num(it.get("mkp")), num(it.get("hipr")), num(it.get("lopr")),
             num(it.get("clpr")), num(it.get("trqu"))] for it in mine if it.get("basDt")]
    latest = max(mine, key=lambda it: it["basDt"]) if mine else {}
    meta = {"code": code, "kind": "stock"}
    if latest:
        meta.update({"name": latest.get("itmsNm"), "market": latest.get("mrktCtg")})
    added = merge(path, meta, rows)
    name = meta.get("name") or hint
    warn = "" if not hint or not meta.get("name") or hint.replace(" ", "") in meta["name"].replace(" ", "") \
        or meta["name"].replace(" ", "") in hint.replace(" ", "") else f" (이름 다름: 목록 '{hint}' / 실제 '{meta['name']}')"
    status["items"][code] = f"{name} {added}일 추가{warn}"


def krx_list(status: dict) -> None:
    """전체 상장 종목 이름·코드 목록 (편집 화면 검색용). 일주일에 한 번만 새로 받는다."""
    path = ROOT / "market" / "krx_list.json"
    old = load_series(path)
    today = datetime.now(KST)
    if old.get("updated") and (today - datetime.strptime(old["updated"], "%Y-%m-%d").replace(tzinfo=KST)).days < 7:
        status["krx_list"] = f"최신 ({old['updated']}, {len(old.get('items', []))}종목)"
        return
    kospi = load_series(OUT / "KOSPI.json").get("series") or []
    basdt = (kospi[-1][0] if kospi else (today - timedelta(days=3)).strftime("%Y-%m-%d")).replace("-", "")
    rows, page, total = [], 1, None
    while total is None or len(rows) < total:
        items, total = call_full(STOCK_URLS, {"basDt": basdt, "numOfRows": 1000, "pageNo": page, "_kind": "stock"}, status)
        if not items:
            break
        rows += items
        page += 1
        if page > 10:
            break
    out = sorted({(str(it.get("srtnCd", "")).lstrip("A"), it.get("itmsNm", ""), it.get("mrktCtg", "")) for it in rows
                  if it.get("srtnCd")}, key=lambda x: x[0])
    if len(out) < 1000:   # 일부만 받았으면 예전 목록을 지키고 다음에 다시
        status["krx_list"] = f"목록이 너무 짧아 갱신 안 함 ({len(out)}종목, 기준일 {basdt})"
        return
    path.write_text(json.dumps({"updated": today.strftime("%Y-%m-%d"), "basis": iso(basdt),
                                "fields": ["code", "name", "market"], "items": [list(x) for x in out]},
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    status["krx_list"] = f"{len(out)}종목 (기준일 {iso(basdt)})"


def summary(indices: list[str], stocks: dict) -> None:
    """지수 띠와 차트 목록에 쓸 요약 파일 (지금 설정에 있는 것만)"""
    items = []
    for code in list(indices) + list(stocks):
        d = load_series(OUT / f"{code}.json")
        s = d.get("series") or []
        if not s:
            continue
        last, prev = s[-1], (s[-2] if len(s) > 1 else None)
        chg = (last[4] / prev[4] - 1) * 100 if prev and prev[4] and last[4] else None
        items.append({"code": d.get("code"), "name": d.get("name"), "kind": d.get("kind"),
                      "market": d.get("market"), "date": last[0], "close": last[4],
                      "change_pct": round(chg, 2) if chg is not None else None})
    (ROOT / "market" / "summary.json").write_text(
        json.dumps({"items": items, "fx": fx_summary()}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    status = {"run_at": datetime.now(KST).isoformat(timespec="seconds"), "items": {}, "errors": []}
    settings = load_settings()
    stocks = tracked_codes(settings, load_entities())
    if not KEY:
        status["errors"].append("DATA_GO_KR_KEY 가 없음")
    else:
        for code in settings["indices"]:
            try:
                fetch_index(code, INDEX_CATALOG[code], status)
            except Exception as e:  # noqa: BLE001
                status["errors"].append(f"{code}: {scrub(e)}")
        for code, name in stocks.items():
            try:
                fetch_stock(code, name, status)
            except Exception as e:  # noqa: BLE001
                status["errors"].append(f"{code} {name}: {scrub(e)}")
        try:
            krx_list(status)
        except Exception as e:  # noqa: BLE001
            status["errors"].append(f"krx_list: {scrub(e)}")
    summary(settings["indices"], stocks)
    text = json.dumps(status, ensure_ascii=False, indent=1)
    (ROOT / "market" / "status.json").write_text(scrub(text), encoding="utf-8")
    print(scrub(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
