"use client";

/**
 * /pricing — 결제는 설정 카드의 두 번째 칸으로 옮겼다(components/Billing).
 *
 * 주소는 남긴다. 사무실의 잔액 링크 · 설명 탭 · 앱 머리가 이 주소를 쓰고,
 * 밖에서 받은 링크도 있다. 탭 카드 덱은 이 주소를 설정 카드로 돌리고 결제
 * 칸까지 내려 준다(TabDeck 의 `aliases`). 이 파일은 덱 밖에서만 그려진다.
 */
import { Billing } from "@/components/Billing";
import { Screen } from "@/components/ui";

export default function PricingPage() {
  return (
    <Screen>
      <Billing />
    </Screen>
  );
}
