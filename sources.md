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
| Reuters | 시험 예정 (공식 RSS 없음) | 해외 딜 |

## 검증용

- 한국: DART 공시 원문
- 미국: SEC EDGAR (User-Agent에 연락처 명시, 초당 요청 제한 준수)
- 기타: 회사 공식 보도자료

## 인박스 (수동, 선택)

더벨은 자동 수집을 허용하지 않아 자동 대상에서 제외한다.
직접 읽은 기사 중 넣고 싶은 것이 있으면:

1. GitHub에서 이 리포의 Issues → New issue
2. 제목에 기사 제목, 본문에 링크 (메모는 있으면 좋고 없어도 됨)
3. 그대로 등록. 열려 있는 이슈는 전부 인박스로 본다.

다음 날 아침 실행 때 인박스를 먼저 처리하고, 처리한 이슈는 딜 노트 링크를 남긴 뒤 닫는다.
인박스가 비어 있으면 그냥 건너뛴다.

## 알려진 빈틈

- 싱가포르·동남아 딜 전문 매체는 자동 수집을 막고 있어, 당분간 WSJ 등에 걸리는 큰 딜 위주로만 잡힌다.
