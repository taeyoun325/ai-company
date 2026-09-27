"use client";

/**
 * 앱 머리 — 로고 · 메뉴 · 사용자 · 언어.
 *
 * 탭 카드 덱(TabDeck)이 서 있는 네 주소에서는 **그리지 않는다.** 덱이 탭
 * 알약으로 같은 메뉴를 갖고 있고, 언어 · 사용자는 덱 아래 줄로 옮겼다.
 * 머리가 빠진 만큼 카드가 커진다.
 *
 * 덱이 아닌 곳(프로젝트 상세 · 수동 실행 · 재설정 · 확인)과 로그인 전
 * 랜딩에서는 그대로 둔다 — 거기서는 이 머리가 돌아갈 길이고, 랜딩에서는
 * 언어를 바꿀 유일한 자리다.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";

import { LangSwitch, Nav } from "./LangSwitch";
import { isDeckPath } from "./TabDeck";
import { UserMenu } from "./UserMenu";
import { Icon } from "./icons";
import { useAuth } from "@/lib/useAuth";

export function AppHeader() {
  const path = usePathname();
  const { user, required, loading, connectionError } = useAuth();
  // 덱 대신 로그인 화면(랜딩)이나 연결 오류가 **확실히** 설 때만 머리를 그린다 —
  // 거기서는 언어를 바꿀 자리가 이 머리뿐이다. 확인하는 동안은 그리지 않는다:
  // 그리면 로그인한 사람에게 머리가 한 번 떴다 사라진다.
  const gated = !loading && !user && (!!connectionError || required);
  if (isDeckPath(path) && !gated) return null;

  return (
    <header className="z-20 shrink-0 border-b border-line bg-[color:var(--panel)] backdrop-blur-xl">
      {/* 좁은 화면에서 메뉴 글자가 두 줄로 쪼개지던 것을 막는다.
          넘치면 접지 말고 옆으로 밀리게 둔다 — 접으면 어떤 메뉴가
          있는지 자체가 안 보인다. */}
      <nav
        className="flex w-full items-center gap-1 overflow-x-auto px-4 py-2.5
          [-ms-overflow-style:none] [scrollbar-width:none]
          [&>*]:shrink-0 [&_*]:whitespace-nowrap"
      >
        <Link href="/" className="mr-3 flex items-center gap-2.5">
          <span
            className="grid size-8 place-items-center rounded-xl text-white
              shadow-[0_4px_14px_rgba(109,141,255,0.4)] grad-accent"
          >
            <Icon name="building" size={18} />
          </span>
          <span className="text-sm font-bold tracking-tight">AI COMPANY</span>
        </Link>
        <Nav />
        {/* 가장자리에 **붙여둔다** (DAY 22).
            헤더는 넘치면 옆으로 밀리는데(위 주석), 폰에서는 그
            사실을 알 길이 없다. 375px 에서 재보니 이 묶음이 화면
            밖 173px 에 있었다 — 즉 폰에서는 언어를 바꿀 수도,
            사용자 메뉴를 열 수도 없었다. 붙여두면 밀려도 보인다.
            배경을 주는 이유는 밑으로 지나가는 메뉴가 비쳐 보이지
            않게 하려는 것이다. */}
        <span className="sticky right-0 -my-2.5 ml-auto flex items-center
          gap-1 bg-[color:var(--bg)] py-2.5 pl-3">
          <UserMenu />
          <LangSwitch compact />
        </span>
      </nav>
    </header>
  );
}
