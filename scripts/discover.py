"""발견 단계: RSS·OpenDART에서 후보를 모아 키워드로 거르고, (가능하면) 제미나이로 1차 점수를 매긴다.

결과는 candidates/YYYY-MM-DD.json 으로 저장한다.
- 기사 본문이나 요약문은 저장하지 않는다 (제목·링크·점수·짧은 사유만).
- API 키는 환경변수(GitHub Secrets)에서만 읽고, 어떤 출력에도 남기지 않는다.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
USER_AGENT = "deal-archive/1.0 (personal study project; https://github.com/suncow-hub/deal-archive)"

SECRETS = [v for v in (os.environ.get("GEMINI_API_KEY"), os.environ.get("DART_API_KEY")) if v]


def scrub(text: str) -> str:
    """오류 메시지 등에 키가 섞여 있으면 가린다."""
    text = str(text)
    for s in SECRETS:
        text = text.replace(s, "***")
    return re.sub(r"(crtfc_key=|key=)[^&\s]+", r"\1***", text)


def log(msg: str) -> None:
    print(scrub(msg), flush=True)


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config" / "discover.yml").read_text(encoding="utf-8"))


def window_start(now: datetime) -> datetime:
    # 화요일 새벽 실행은 주말까지 포함, 그 외엔 하루 + 여유
    hours = 78 if now.weekday() == 1 else 30
    return now - timedelta(hours=hours)


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def keyword_hits(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    hits = []
    for w in words:
        wl = str(w).lower()
        if re.fullmatch(r"[a-z]+", wl):
            if re.search(rf"\b{re.escape(wl)}\b", low):
                hits.append(w)
        elif wl in low:
            hits.append(w)
    return hits


# ---------------------------------------------------------------- RSS

def fetch_feeds(cfg: dict, since: datetime, stats: dict) -> list[dict]:
    out = []
    deal_words = cfg["deal_keywords"]["en"] + cfg["deal_keywords"]["ko"]
    macro_words = cfg["macro_keywords"]["en"] + cfg["macro_keywords"]["ko"]
    for feed in cfg["feeds"]:
        name = feed["name"]
        try:
            r = requests.get(feed["url"], headers={"User-Agent": USER_AGENT}, timeout=20)
            r.raise_for_status()
            parsed = feedparser.parse(r.content)
        except Exception as e:  # noqa: BLE001
            stats[name] = f"실패: {scrub(type(e).__name__)}"
            log(f"[{name}] 가져오기 실패: {e}")
            continue

        kept = total = 0
        for entry in parsed.entries:
            total += 1
            ts = entry.get("published_parsed") or entry.get("updated_parsed")
            published = datetime(*ts[:6], tzinfo=timezone.utc) if ts else None
            if published and published < since:
                continue
            title = clean(entry.get("title", ""))
            snippet = clean(entry.get("summary", ""))[:400]
            text = f"{title} {snippet}"
            words = deal_words if feed["kind"] == "deal" else macro_words
            hits = keyword_hits(text, words)
            if not hits:
                continue
            item = {
                "source": name,
                "kind": feed["kind"],
                "title": title,
                "link": entry.get("link", ""),
                "published": published.astimezone(KST).isoformat() if published else None,
                "keywords": hits[:5],
                "_snippet": snippet,  # 점수 매길 때만 쓰고 저장하지 않음
            }
            if name.startswith("PR Newswire") and not keyword_hits(text, cfg["prn_size_signals"]):
                item["small"] = True
            out.append(item)
            kept += 1
        stats[name] = f"{kept}/{total}"
        log(f"[{name}] {total}건 중 {kept}건 통과")
    return out


# ---------------------------------------------------------------- OpenDART

def fetch_dart(cfg: dict, since: datetime, now: datetime, stats: dict) -> list[dict]:
    key = os.environ.get("DART_API_KEY")
    if not key:
        stats["OpenDART"] = "키 없음"
        log("[OpenDART] 키가 없어 건너뜀")
        return []

    dcfg = cfg["dart"]
    out = []
    for ty, words in (("B", dcfg["report_keywords"]), ("I", dcfg["exchange_keywords"])):
        page = 1
        while True:
            params = {
                "crtfc_key": key,
                "bgn_de": since.astimezone(KST).strftime("%Y%m%d"),
                "end_de": now.strftime("%Y%m%d"),
                "pblntf_ty": ty,
                "page_no": page,
                "page_count": 100,
            }
            try:
                r = requests.get("https://opendart.fss.or.kr/api/list.json", params=params,
                                 headers={"User-Agent": USER_AGENT}, timeout=20)
                data = r.json()
            except Exception as e:  # noqa: BLE001
                stats[f"OpenDART-{ty}"] = f"실패: {type(e).__name__}"
                log(f"[OpenDART-{ty}] 요청 실패: {e}")
                break
            status = data.get("status")
            if status == "013":  # 조회된 데이터 없음
                break
            if status != "000":
                stats[f"OpenDART-{ty}"] = f"오류 {status}: {data.get('message')}"
                log(f"[OpenDART-{ty}] 오류 {status}: {data.get('message')}")
                break
            for row in data.get("list", []):
                if row.get("corp_cls") not in dcfg["corp_classes"]:
                    continue
                name = row.get("report_nm", "")
                hits = [w for w in words if w in name.replace(" ", "") or w in name]
                if not hits:
                    continue
                rcept = row.get("rcept_no", "")
                out.append({
                    "source": "OpenDART",
                    "kind": "deal",
                    "title": f"({row.get('corp_name')}) {name.strip()}",
                    "link": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept}",
                    "published": datetime.strptime(row.get("rcept_dt"), "%Y%m%d").replace(tzinfo=KST).isoformat(),
                    "keywords": hits,
                    "_snippet": f"공시 제출인: {row.get('flr_nm')}",
                })
            if page >= int(data.get("total_page", 1)):
                break
            page += 1
    # 정정 공시는 같은 회사·같은 공시의 원본이 이미 있으면 뺀다
    def base(title: str) -> str:
        return re.sub(r"\[[^\]]*\]", "", title).replace(" ", "")
    originals = {base(it["title"]) for it in out if "정정" not in it["title"]}
    out = [it for it in out if "정정" not in it["title"] or base(it["title"]) not in originals]
    stats["OpenDART"] = f"{len(out)}건"
    log(f"[OpenDART] 딜 관련 공시 {len(out)}건")
    return out


# ---------------------------------------------------------------- 중복 제거

def previous_links(days: int = 5) -> set[str]:
    links = set()
    today = f"{datetime.now(KST):%Y-%m-%d}.json"
    files = [f for f in sorted((ROOT / "candidates").glob("*.json")) if f.name != today][-days:]
    for f in files:
        try:
            for it in json.loads(f.read_text(encoding="utf-8")).get("items", []):
                links.add(it.get("link"))
        except Exception:  # noqa: BLE001
            pass
    return links


def dedupe(items: list[dict]) -> list[dict]:
    seen_links, seen_titles, out = previous_links(), set(), []
    for it in items:
        norm = re.sub(r"\W+", "", it["title"].lower())
        if it["link"] in seen_links or norm in seen_titles:
            continue
        seen_links.add(it["link"])
        seen_titles.add(norm)
        out.append(it)
    return out


# ---------------------------------------------------------------- 점수

def heuristic_score(it: dict) -> float:
    if it["source"] == "OpenDART":
        return 7.0
    score = 3.0 + min(len(it["keywords"]), 3)
    if it.get("small"):
        score -= 3
    return score


GEMINI_PROMPT = """너는 한국 대학생이 IB(M&A) 취업을 준비하며 보는 딜 아카이브의 1차 선별 담당이다.
아래 후보 각각에 대해 판단해라.

- kind: "deal"(M&A·지분투자·IPO·자본조달 등 실제 거래), "macro"(딜과 금리·환율·규제에 영향을 주는 거시·국제정치 뉴스), "drop"(관련 없음, 시장 시황 단순 보도, 개인 재테크 등)
- score: 0~10. 거래 규모가 크거나, 한국 시장·기업이 걸려 있거나, 업계 흐름을 보여주거나, 금융권 취업 준비생이 알아둘 가치가 클수록 높게.
  소규모 비상장사 간 거래, 단순 루머 반복, 같은 딜의 중복 보도는 낮게.
- reason: 한국어 한 문장(30자 이내).

JSON 배열로만 답해라: [{"id": 0, "kind": "deal", "score": 7, "reason": "..."}]

후보:
"""


def pick_model(client) -> str:
    if os.environ.get("GEMINI_MODEL"):
        return os.environ["GEMINI_MODEL"]
    names = []
    for m in client.models.list():
        n = m.name.split("/")[-1]
        actions = getattr(m, "supported_actions", None) or []
        if (not actions or "generateContent" in actions) and "flash" in n and not re.search(r"image|tts|audio|live|lite|exp", n):
            names.append(n)
    if not names:
        raise RuntimeError("사용 가능한 flash 모델을 찾지 못함")
    names.sort(key=lambda n: (("preview" in n), [-int(x) if x.isdigit() else 0 for x in re.findall(r"\d+", n)]))
    return names[0]


def gemini_score(items: list[dict], meta: dict) -> bool:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        meta["gemini"] = "키 없음"
        return False
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        model = pick_model(client)
        meta["gemini_model"] = model
        lines = [f'{i}. [{it["source"]}] {it["title"]} | {it["_snippet"][:200]}' for i, it in enumerate(items)]
        resp = client.models.generate_content(
            model=model,
            contents=GEMINI_PROMPT + "\n".join(lines),
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
        )
        results = json.loads(resp.text)
        by_id = {int(r["id"]): r for r in results if "id" in r}
        for i, it in enumerate(items):
            r = by_id.get(i)
            if r:
                it["score"] = float(r.get("score", 0))
                it["reason"] = str(r.get("reason", ""))[:60]
                if r.get("kind") in ("deal", "macro", "drop"):
                    it["kind"] = r["kind"]
                it["score_by"] = "gemini"
        meta["gemini"] = f"성공 ({len(by_id)}/{len(items)}건 채점)"
        log(f"[Gemini] {model}로 {len(by_id)}/{len(items)}건 채점")
        return True
    except Exception as e:  # noqa: BLE001
        meta["gemini"] = f"실패: {scrub(type(e).__name__)}: {scrub(str(e))[:200]}"
        log(f"[Gemini] 실패 → 키워드 점수로 진행: {e}")
        return False


# ---------------------------------------------------------------- 메인

def main() -> int:
    cfg = load_config()
    now = datetime.now(KST)
    since = window_start(now)
    stats: dict = {}
    meta: dict = {"run_at": now.isoformat(), "window_start": since.isoformat(), "sources": stats}

    items = fetch_dart(cfg, since, now, stats) + fetch_feeds(cfg, since, stats)
    items = dedupe(items)
    for it in items:
        it["score"] = heuristic_score(it)
        it["score_by"] = "keyword"
        it["reason"] = ""

    scored = False
    if items:
        scored = gemini_score(items, meta)
    else:
        meta["gemini"] = "후보 없음"

    lim = cfg["limits"]
    min_deal = lim["min_score_deal"] if scored else 0
    min_macro = lim["min_score_macro"] if scored else 0
    deals = sorted([i for i in items if i["kind"] == "deal" and i["score"] >= min_deal],
                   key=lambda x: -x["score"])[: lim["max_candidates_deal"]]
    macros = sorted([i for i in items if i["kind"] == "macro" and i["score"] >= min_macro],
                    key=lambda x: -x["score"])[: lim["max_candidates_macro"]]
    meta["counts"] = {"deal": len(deals), "macro": len(macros),
                      "dropped": len(items) - len(deals) - len(macros)}

    kept = []
    for it in deals + macros:
        it.pop("_snippet", None)
        it.pop("small", None)
        kept.append(it)

    out_dir = ROOT / "candidates"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{now:%Y-%m-%d}.json"
    out.write_text(json.dumps({"meta": meta, "items": kept}, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"저장: {out.relative_to(ROOT)} (딜 {len(deals)}, 기타 {len(macros)})")
    log(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
