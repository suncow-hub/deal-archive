# 수집 소스

자동 수집은 공식 RSS·API처럼 자동 접근이 허용된 곳만 사용한다.
사이트가 자동 수집을 막고 있으면(robots.txt 등) 자동 수집하지 않는다.
기사 본문은 저장하지 않고, 딜 노트에는 우리가 정리한 내용과 원문 링크만 남긴다.

## 발견용 (자동)

| 소스 | 방식 | 용도 |
|---|---|---|
| WSJ Markets | RSS `feeds.content.dowjones.io/public/rss/RSSMarketsMain` | 해외 딜 |
| WSJ U.S. Business | RSS `feeds.content.dowjones.io/public/rss/WSJcomUSBusiness` | 해외 딜 |
| WSJ World News | RSS `feeds.content.dowjones.io/public/rss/RSSWorldNews` | 딜 외 뉴스 (국제정치) |
| WSJ Economy | RSS `feeds.content.dowjones.io/public/rss/socialeconomyfeed` | 딜 외 뉴스 (거시경제) |
| 한경 증권 | RSS `www.hankyung.com/feed/finance` | 한국 딜 (마켓인사이트 포함 여부 시험 중) |
| 한경 경제·국제 | RSS `www.hankyung.com/feed/economy`, `/international` | 딜 외 뉴스 |
| OpenDART | API (Secrets: `DART_API_KEY`) | 한국 딜 1차 자료 (합병·인수·영업양수도 공시) |
| PR Newswire M&A | RSS (Acquisitions, Mergers and Takeovers) | 해외 딜 1차 자료, 소규모 딜 필터 필수 |
| Reuters | 제외 (공식 RSS 없음, 우회 경로인 구글 뉴스 RSS도 자동 수집 불허) | — |
| 인베스트조선 | RSS `www.investchosun.com/rss/` | 국내 IB·PE 딜 (예비입찰·우협 등 공시 전 단계) |
| 연합뉴스 마켓+ | RSS `www.yna.co.kr/rss/market.xml` | 국내 딜·IPO |
| 매일경제 증권 | RSS `www.mk.co.kr/rss/50200011/` | 국내 딜 |
| 조선비즈 | RSS `biz.chosun.com/arc/outboundfeeds/rss/` | 국내 딜 (키워드 필터) |
| FT M&A | RSS `www.ft.com/mergers-acquisitions?format=rss` | 유럽·글로벌 딜 (제목만, 본문 유료) |
| CNBC Business | RSS `www.cnbc.com/id/10001147/...` | 미국 딜 |

## 검증용

- 한국: DART 공시 원문
- 미국: SEC EDGAR (User-Agent에 연락처 명시, 초당 요청 제한 준수)
- 기타: 회사 공식 보도자료

## 인박스 (수동, 선택)

더벨은 자동 수집을 허용하지 않아 자동 대상에서 제외한다.
직접 읽은 기사 중 넣고 싶은 것이 있으면:

1. GitHub에서 이 리포의 Issues → New issue
2. 제목에 기사 제목, 본문에 링크 (메모는 있으면 좋고 없어도 됨)
3. 그대로 등록. 리포 소유자(suncow-hub)가 만든 열린 이슈만 인박스로 본다.

다음 날 아침 실행 때 인박스를 먼저 처리하고, 처리한 이슈는 딜 노트 링크를 남긴 뒤 닫는다.
인박스가 비어 있으면 그냥 건너뛴다.

## 시험했지만 쓰지 않는 소스 (2026-11-02 source-probe)

| 소스 | 이유 |
|---|---|
| Business Wire | robots.txt가 자동 수집 차단 |
| GlobeNewswire, SEC EDGAR 피드 | 자동 접근 거부(403) |
| 딜사이트, AsianInvestor, Korea Herald | 피드가 비어 있음 |
| 서울경제, Investegate | 피드 주소 없음(404) |
| 이데일리 | 연결 실패 |
| 머니투데이, Nikkei Asia | 피드는 오지만 딜 기사가 걸리지 않음 |
| Gemini 검색(grounding) | 무료 키에서는 검색 기능 사용량이 0으로 막혀 있음(429). 결제 계정 연결이 필요해 보류 |

## 보조 발견 (검색)

새벽 검증 단계가 하루 최대 3번 웹 검색으로 피드에 없는 큰 딜(아시아, 글로벌 대형 딜 등)을 찾는다. 사이트를 긁는 것이 아니라 검색엔진 결과를 보는 것이라 robots 규칙과 충돌하지 않는다. 자세한 규칙은 `agents/verify.md`.

## 알려진 빈틈

- 싱가포르·동남아 딜 전문 매체는 자동 수집을 막고 있어, 당분간 WSJ 등에 걸리는 큰 딜 위주로만 잡힌다.
