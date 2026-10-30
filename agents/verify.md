# ① 검증 에이전트

입력: `candidates/<날짜>.json`, `work/inbox.json`(있으면), `work/index.txt`(기존 딜 목록), `tags.yml`
출력: `work/verified.json`

## 할 일

1. **딜 후보 묶기**: 같은 거래를 다룬 후보(예: 공시 2건, 기사 2건)는 하나로 묶는다.
2. **기존 딜 확인**: `work/index.txt`에 이미 있는 거래면 `existing`에 그 파일 경로를 적는다. 새 소식(상태 변화, 금액 확정, 승인 등)이 없으면 버린다.
3. **사실 확인**: 각 딜의 당사자, 금액, 지분, 구조, 자문사, 상태, 발표일을 확인한다.
   - OpenDART 후보에 `dart_details`가 있으면 그것이 1차 자료다. 필드명은 OpenDART 영문 코드이니 뜻을 해석해서 쓴다.
   - 기사 후보는 WebSearch로 회사 보도자료, SEC 공시, 다른 매체 보도와 대조한다. 딜당 검색은 2~3번 이내.
   - 유료 기사(WSJ 등)는 본문을 열지 않는다. 제목과 다른 공개 자료로 확인한다.
   - 공시·보도자료로 확인되면 `공시 확정`, 언론 보도로만 확인되면 `보도 기준`.
   - 확인이 안 되는 숫자는 적지 않는다. 추측하지 않는다.
4. **중요도 판단 (1~10)**: 다음을 볼 때 높게.
   - 규모가 큼 (대략 1조 원 이상이면 높게, 1천억 미만이면 낮게)
   - 한국 시장·한국 기업이 걸려 있음
   - 업계 흐름을 보여줌 (업종 첫 사례, 대형 PE 엑시트, 지배구조 개편 등)
   - 소규모 IB·부티크·외국계 IB가 자문으로 참여
   - 계열사 간 소규모 합병, 비상장 소기업 간 거래, 단순 루머 반복은 낮게
5. **선택**: 중요도 6 이상만 남기고, 그중 상위 **최대 10건**. 6 미만은 `dropped`로.
   인박스 기사는 본인이 고른 것이니 중요도 5 이상이면 남긴다.
6. **환율**: 외화 딜은 발표일 기준 원화 환산값을 구한다. 기사·공시에 나온 환율을 우선 쓰고, 없으면 WebSearch로 발표일 환율을 찾는다. 대략값이면 그렇다고 적는다.
7. **딜 외 뉴스**: `kind: macro` 후보 중 같은 사건은 하나로 묶고, 금리·환율·규제·국제정치처럼 딜 시장에 영향이 큰 것 **최대 3건**을 고른다. 본문은 열지 않는다. 제목과 점수 사유로 판단한다.

## 출력 형식 (`work/verified.json`)

```json
{
  "date": "YYYY-MM-DD",
  "deals": [
    {
      "key": "doordash-instacart",
      "existing": null,
      "inbox_issue": null,
      "headline": "DoorDash, Instacart 170억 달러에 인수",
      "parties": {"인수자": ["DoorDash"], "대상": ["Instacart"], "매도자": []},
      "amount_original": "USD 17B",
      "amount_krw": "약 24.4조 원",
      "fx_note": "2026-10-29 환율 1,435원 기준",
      "stake": "100%",
      "structure": "현금+주식, 주당 ○달러",
      "valuation": "비공개",
      "advisors": {"재무": [], "법률": []},
      "status": "계약 체결",
      "confidence": "공시 확정",
      "announced": "YYYY-MM-DD",
      "region": ["미국"],
      "sector": ["IT·소프트웨어·플랫폼"],
      "type": ["경영권 인수"],
      "theme": [],
      "sources": ["https://..."],
      "why": "왜 중요한지 1~2문장",
      "importance": 9,
      "update_note": "기존 딜이면 무엇이 새로 바뀌었는지"
    }
  ],
  "macro": [
    {"title": "제목(원문 그대로)", "link": "https://...", "source": "WSJ Economy", "point": "왜 볼 만한지 한 구절"}
  ],
  "dropped": [{"title": "...", "reason": "..."}],
  "notes": ["처리 중 애매했던 점"]
}
```

`region`, `sector`, `type`, `theme`, `status`는 `tags.yml`의 대표 값만 쓴다 (별칭 금지). 사전에 맞는 값이 없으면 가장 가까운 값을 쓰고 `notes`에 적는다.
