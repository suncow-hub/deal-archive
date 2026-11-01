"""새 소스 후보 시험: robots.txt 허용 여부, 피드 응답, 항목 수, 최신 날짜, 딜 키워드 예시.
그리고 Gemini 검색(grounding)이 무료 키로 동작하는지 확인한다. 결과는 JSON으로 출력 (키는 남기지 않음)."""

import json
import os
import re
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
import requests

UA = "deal-archive/1.0 (personal study project; https://github.com/suncow-hub/deal-archive)"
DEAL = re.compile(r"인수|매각|합병|M&A|지분|우선협상|사모펀드|PEF|IPO|상장|acqui|merger|takeover|buyout|stake|deal", re.I)

FEEDS = [
    # 국내
    ("연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml"),
    ("연합뉴스 마켓+", "https://www.yna.co.kr/rss/market.xml"),
    ("매일경제 증권", "https://www.mk.co.kr/rss/50200011/"),
    ("매일경제 경제", "https://www.mk.co.kr/rss/30100041/"),
    ("이데일리 증권", "https://rss.edaily.co.kr/stock_news.xml"),
    ("머니투데이", "https://rss.mt.co.kr/mt_news.xml"),
    ("서울경제 증권", "https://www.sedaily.com/RSS/Stock"),
    ("조선비즈", "https://biz.chosun.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("딜사이트", "https://dealsite.co.kr/rss/allArticle.xml"),
    ("인베스트조선", "https://www.investchosun.com/rss/"),
    ("Korea Herald 비즈", "https://www.koreaherald.com/rss/020200000000.xml"),
    # 해외
    ("FT M&A", "https://www.ft.com/mergers-acquisitions?format=rss"),
    ("FT Companies", "https://www.ft.com/companies?format=rss"),
    ("CNBC Business", "https://www.cnbc.com/id/10001147/device/rss/rss.html"),
    ("Nikkei Asia", "https://asia.nikkei.com/rss/feed/nar"),
    ("AsianInvestor", "https://asianinvestor.net/rss"),
    ("GlobeNewswire M&A", "https://www.globenewswire.com/RssFeed/subjectcode/27-Mergers%20And%20Acquisitions/feedTitle/GlobeNewswire%20-%20Mergers%20And%20Acquisitions"),
    ("Business Wire M&A", "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeEF9YXA=="),
    ("SEC 8-K (EDGAR)", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&count=40&output=atom"),
    ("Investegate (UK)", "https://www.investegate.co.uk/rss"),
]


def robots_ok(url: str) -> str:
    p = urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = requests.get(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": UA}, timeout=15)
        if r.status_code >= 400:
            return "robots 없음(허용)"
        rp.parse(r.text.splitlines())
        path = p.path + (("?" + p.query) if p.query else "")
        return "허용" if rp.can_fetch(UA, path or "/") else "차단"
    except Exception as e:  # noqa: BLE001
        return f"robots 확인 실패: {type(e).__name__}"


def probe_feed(name: str, url: str) -> dict:
    out = {"name": name, "url": url, "robots": robots_ok(url)}
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        out["http"] = r.status_code
        f = feedparser.parse(r.content)
        out["items"] = len(f.entries)
        dates = [e.get("published_parsed") or e.get("updated_parsed") for e in f.entries]
        dates = [datetime(*d[:6]).isoformat() for d in dates if d]
        out["latest"] = max(dates) if dates else None
        hits = [e.get("title", "") for e in f.entries if DEAL.search(e.get("title", ""))]
        out["deal_hits"] = len(hits)
        out["samples"] = hits[:4]
    except Exception as e:  # noqa: BLE001
        out["error"] = type(e).__name__
    return out


def probe_grounding() -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return {"error": "키 없음"}
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    res = {}
    try:
        plain = client.models.generate_content(model="gemini-flash-latest", contents="1+1=?")
        res["plain_call"] = "ok: " + (plain.text or "")[:20]
    except Exception as e:  # noqa: BLE001
        res["plain_call"] = f"{type(e).__name__}: {str(e)[:160]}".replace(key, "***")
    qs = {
        "kr": "지난 24시간 동안 한국에서 보도된 M&A·사모펀드·인수 관련 주요 소식(예비입찰, 우선협상대상자 선정, 매각 추진 등)을 매체 이름과 함께 5개 이내로 나열해줘.",
        "asia": "List up to 5 notable M&A or private equity deals in Asia (excluding Korea) reported in the last 24 hours, with the outlet name for each.",
    }
    for model in ("gemini-3.8-flash", "gemini-flash-latest"):
        try:
            for k, q in qs.items():
                resp = client.models.generate_content(
                    model=model, contents=q,
                    config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=0.2),
                )
                gm = resp.candidates[0].grounding_metadata if resp.candidates else None
                chunks = (gm.grounding_chunks or []) if gm else []
                srcs = []
                for c in chunks[:8]:
                    w = c.web
                    final = None
                    try:
                        final = requests.get(w.uri, headers={"User-Agent": UA}, timeout=15, allow_redirects=True).url
                    except Exception:  # noqa: BLE001
                        pass
                    srcs.append({"title": w.title, "final_url": final})
                res[k] = {"model": model, "text": (resp.text or "")[:700], "sources": srcs,
                          "queries": list(gm.web_search_queries or []) if gm else []}
            return res
        except Exception as e:  # noqa: BLE001
            res[f"error_{model}"] = f"{type(e).__name__}: {str(e)[:200]}".replace(key, "***")
    return res


if __name__ == "__main__":
    only_g = os.environ.get("ONLY_GROUNDING") == "1"
    out = {"run_at": datetime.now(timezone.utc).isoformat(), "feeds": [] if only_g else [probe_feed(n, u) for n, u in FEEDS],
           "grounding": probe_grounding()}
    print(json.dumps(out, ensure_ascii=False, indent=1))
