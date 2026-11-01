"""한국 시세 수집: 금융위원회 공공데이터 API로 KOSPI·KOSDAQ 지수와 관심 종목의 일별 시세를 쌓는다.

- 관심 종목 = market/watchlist.yml + entities.yml 에서 krx 코드가 있는 회사
- 종목마다 market/kr/<코드>.json, 지수는 market/kr/KOSPI.json, KOSDAQ.json
- 처음 보는 종목은 1년치를 한 번에 받고, 이후엔 새 날짜만 덧붙인다
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
import yaml

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
INDICES = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}


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
    """여러 주소를 차례로 시도. 성공한 주소는 기억해서 다음부터 먼저 쓴다."""
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
            return items
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
    items = call(INDEX_URLS, {"idxNm": name, "beginBasDt": begin, "endBasDt": end, "numOfRows": 1000,
                              "pageNo": 1, "_kind": "index"}, status)
    rows = [[iso(it["basDt"]), num(it.get("mkp")), num(it.get("hipr")), num(it.get("lopr")),
             num(it.get("clpr")), num(it.get("trqu"))]
            for it in items if it.get("idxNm") == name and it.get("basDt")]
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


def watchlist() -> dict[str, str]:
    """{코드: 이름} — watchlist.yml + entities.yml 의 krx 코드"""
    out: dict[str, str] = {}
    wl = ROOT / "market" / "watchlist.yml"
    for row in (yaml.safe_load(wl.read_text(encoding="utf-8")) or []) if wl.exists() else []:
        code = str(row.get("code", "")).strip().zfill(6)
        if re.fullmatch(r"\d{6}|[0-9A-Z]{6}", code):
            out[code] = str(row.get("name", ""))
    ents = yaml.safe_load((ROOT / "entities.yml").read_text(encoding="utf-8")) or {}
    for name, info in ents.items():
        code = str((info or {}).get("krx", "") or "").strip()
        if code:
            out.setdefault(code.zfill(6), name)
    return out


def summary() -> None:
    """지수 띠와 차트 검색 목록에 쓸 요약 파일"""
    items = []
    for p in sorted(OUT.glob("*.json")):
        d = load_series(p)
        s = d.get("series") or []
        if not s:
            continue
        last, prev = s[-1], (s[-2] if len(s) > 1 else None)
        chg = (last[4] / prev[4] - 1) * 100 if prev and prev[4] and last[4] else None
        items.append({"code": d.get("code"), "name": d.get("name"), "kind": d.get("kind"),
                      "market": d.get("market"), "date": last[0], "close": last[4],
                      "change_pct": round(chg, 2) if chg is not None else None})
    items.sort(key=lambda x: (x["kind"] != "index", x["name"] or ""))
    fx = {}
    fxp = ROOT / "market" / "fx.json"
    if fxp.exists():
        rates = json.loads(fxp.read_text(encoding="utf-8")).get("rates", {})
        days = sorted(rates)
        if days:
            cur, prev = rates[days[-1]], rates[days[-2]] if len(days) > 1 else None
            fx = {"date": days[-1], "USD": cur.get("USD"),
                  "USD_change_pct": round((cur["USD"] / prev["USD"] - 1) * 100, 2) if prev and prev.get("USD") else None}
    (ROOT / "market" / "summary.json").write_text(
        json.dumps({"items": items, "fx": fx}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    status = {"run_at": datetime.now(KST).isoformat(timespec="seconds"), "items": {}, "errors": []}
    if not KEY:
        status["errors"].append("DATA_GO_KR_KEY 가 없음")
    else:
        for code, name in INDICES.items():
            try:
                fetch_index(code, name, status)
            except Exception as e:  # noqa: BLE001
                status["errors"].append(f"{code}: {scrub(e)}")
        for code, name in watchlist().items():
            try:
                fetch_stock(code, name, status)
            except Exception as e:  # noqa: BLE001
                status["errors"].append(f"{code} {name}: {scrub(e)}")
    summary()
    text = json.dumps(status, ensure_ascii=False, indent=1)
    (ROOT / "market" / "status.json").write_text(scrub(text), encoding="utf-8")
    print(scrub(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
