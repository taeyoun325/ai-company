# 바깥에서 파는 것들 — 조사와 그래서 무엇을 할까 (DAY 22)

조사일 2026-09-22. 값은 바뀐다. 오래됐으면 다시 봐야 한다.

---

## 1. 가격이 어디에 모여 있나

| | 진입가 | 방식 |
|---|---|---|
| Devin | **$20** (출시 때 $500 → 내려옴, Max $200) | 구독 |
| Replit Core | **$25** ($20 연간) · Pro $100 | 구독 + 크레딧 + 초과 종량 |
| Lovable Starter | **$25** (무료 1개 프로젝트) | 구독 + 생성 횟수 |
| Cursor | **$20** | 구독 |
| 공통 | **$200** 대에서는 사실상 무제한 | — |

**읽을 것 두 가지.**

진입가가 $20~25 에 몰려 있다. 우리 스타터는 $29 다 — 시장보다 위다.
그 자리에서 이기려면 "더 싸다"가 아니라 **"이건 다른 물건이다"**를
말해야 한다. 우리가 가진 다른 물건은 교차검증(§8)과 테스트 선작성(§9)
이다. 랜딩과 요금제 화면이 그걸 먼저 말해야 한다.

진짜 경쟁은 $200 이 아니라 $20 에서 벌어진다. 그 가격대에서는 한도가
빡빡해서 **"어떤 작업에 좋은 모델을 쓸까"를 사용자가 고민**하게 된다.
우리 제품은 그 고민을 대신 해준다(직원마다 모델이 다르고, 비싼 모델은
비싼 자리에만 있다). 이건 팔 수 있는 이야기다.

## 2. 사람들이 실제로 불평하는 것

조사에서 반복해서 나온 문장: **"크레딧이 얼마인지는 알겠는데, 그게 뭘
사주는지는 모르겠다."** Replit 이 대표적으로 지적당한다 — 월 크레딧
금액은 예측 가능한데 그것이 몇 개의 작업을 사주는지는 예측 불가능하다.

이건 우리가 지금 **똑같이 갖고 있는 문제**다. 요금제 화면의 "월 N건
(추정)"은 추정이고, 아직 실제 모델로 프로젝트를 완주해본 적이 없다
(STATUS.md). 다른 점은 하나뿐이다 — 우리는 그게 추정이라고 화면에
적었다.

그 다음으로 반복된 것:

- **"자율 에이전트 인력"이라는 광고와 실제 운영 결과의 간극.** 크레딧
  소진 속도, 도입 기간, 통제 문제.
- **가격을 공개하지 않고 "영업팀에 문의"로 보내는 것.**
- 보안·설명가능성·감사 가능성·데이터 계보가 구매 기준으로 올라왔다.
  실행을 되짚어 디버깅하고, 접근 권한을 빨리 회수할 수 있는지를 본다.

## 3. 그래서 우리가 할 일

### 이미 갖고 있어서 **말만 하면 되는 것**

| 우리 것 | 어느 불평에 답하나 |
|---|---|
| 교차검증 — 다른 회사 모델이 판정 | "에이전트가 자기 일을 자기가 검사한다" |
| 테스트 선작성 · 구현자는 tests/ 를 못 읽음 | 같은 위 |
| 파일별 작성자 · 회차별 diff | 감사 가능성 · 데이터 계보 |
| 권한 경계가 코드로 강제 | 통제 · 권한 회수 |
| 호출 **전** 비용 차단, 요금제별 상한 | 크레딧 소진 속도 |
| 공개된 가격표, 영업 문의 없음 | 가격 불투명 |
| Mock 을 숨기지 않음 · 못 하는 것을 랜딩에 적음 | 광고와 실제의 간극 |

### 아직 없어서 **만들어야 하는 것** (우선순위)

1. **크레딧이 무엇을 사주는지 실측으로 말하기.** 지금은 추정이다.
   키가 들어오면 프로젝트 10건을 돌려 중앙값·p90 을 뽑고, 요금제
   화면의 "월 N건"을 실측으로 바꾼다. 이게 1번인 이유는, 이게 시장
   전체가 못 하고 있는 것이고 우리는 이미 원가를 호출 단위로 집계하고
   있기 때문이다. **가장 싸게 만들 수 있는 차별점이다.**
2. **실행 기록을 되짚을 수 있게.** 지금도 이벤트는 남지만 화면에서
   "이 파일을 누가, 몇 회차에, 어떤 지적을 받고 고쳤나"를 한 번에
   따라가지 못한다.
3. **결제.** 크레딧은 실제로 줄지만 충전은 데모 버튼이다.
4. **초과 사용 처리.** 경쟁사는 대부분 종량으로 넘긴다. 우리는 지금
   그냥 멈춘다 — 멈추는 쪽이 안전하지만, 급한 사용자에게는 그 자리에서
   더 살 수 있어야 한다.
5. **비밀번호 재설정 · 이메일 인증.** 팔기 전에 필요하다.

### 하지 않기로 한 것

- **"무제한" 요금제.** $200 대에서 무제한을 파는 곳이 많지만, 우리
  원가는 모델 호출에 그대로 비례한다. 무제한은 우리가 감당할 수 없는
  약속이고, 감당 못 할 약속은 파는 게 아니라 빌리는 것이다.
- **무료 요금제.** DAY 19 에 없앴다. 이유는 STATUS.md 에 있다.

---

## 출처

- [8 Best Devin AI Alternatives in 2026](https://www.taskade.com/blog/devin-ai-alternatives)
- [Replit Pricing Breakdown 2026 — Superblocks](https://www.superblocks.com/blog/replit-pricing)
- [Replit Pricing 2026: Plans, Credits & Hidden Costs — No Code MBA](https://www.nocode.mba/articles/replit-pricing)
- [AI Coding Subscription Plans Compared (2026) — AiCybr](https://aicybr.com/blog/ai-coding-subscription-plans-comparison)
- [7 Coding Agents, 1 Budget — AI Cost Estimator](https://ai-cost-estimator.com/blog/7-coding-agents-cost-comparison-2026-claude-cursor-copilot-devin-codex-grok-replit)
- [How to Improve SaaS Product Adoption in 2026 — Userpilot](https://userpilot.com/blog/product-adoption-saas/)
- [Top 5 Solutions for AI and Agentic monetization — Flexprice](https://flexprice.io/blog/top-solutions-for-ai-and-agentic-monetization)
- [16 Best AI Agents 2026 — Toolworthy](https://www.toolworthy.ai/blog/best-ai-agents)
