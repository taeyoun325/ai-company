import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { LangPartialNote, LangSwitch, Nav, VerifyNote }
  from "@/components/LangSwitch";
import { UserMenu } from "@/components/UserMenu";
import { Icon } from "@/components/icons";
import { LangProvider } from "@/lib/i18n";
import { AuthProvider } from "@/lib/useAuth";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

// 링크 미리보기와 검색 결과에 나가는 한 줄.
//
// **한 번 동적으로 만들어 봤다가 되돌렸다** (DAY 22). `headers()` 로
// `Accept-Language` 를 읽어 세 언어로 나눠 보냈는데, 그러면 루트 레이아웃이
// 동적이 되어 **앱 전체의 정적 프리렌더가 사라진다.** 재보고 안 결과다:
//
//   before: ○ / · /pricing · /projects · /settings · /reset · /verify · 404
//   after:  ƒ 전부 (server-rendered on demand)
//
// 랜딩(`/`)은 이 제품의 **유일한 공개 페이지**이자 판매 창구다. 그걸 CDN 에
// 못 얹는 대가로 얻는 것은, 링크를 공유했을 때의 설명 한 줄뿐이다. 게다가
// 링크 미리보기 봇(Slack·Twitter 등)은 대개 `Accept-Language` 를 보내지
// 않으므로 어차피 기본값이 나간다 — 값에 비해 대가가 크다.
//
// 화면 글자는 전부 번역돼 있고, 이 한 줄만 한국어로 고정이다.
export const metadata: Metadata = {
  title: "AI COMPANY",
  description: "AI 직원들이 실제 회사처럼 협업합니다. 당신은 CEO 입니다.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/*
          스크립트가 꺼져 있으면 등장 애니메이션은 영영 돌지 않는다.
          그 상태에서 시작 상태(opacity 0)가 남으면 **글이 통째로 사라진
          화면**이 된다. 되돌린다.
        */}
        <noscript>
          <style>{`[data-reveal]{opacity:1 !important}`}</style>
        </noscript>
      </head>
      {/*
        화면이 창 높이에 딱 맞는다(`h-full` + `overflow-hidden`). 사무실은
        한 눈에 보이는 작업대여야 하고, 작업대가 스크롤되면 로그를 보는
        동안 사무실이 화면 밖으로 나간다. 안쪽 칸만 각자 스크롤한다.
      */}
      <body className="flex h-full flex-col overflow-hidden">
        <LangProvider>
        <AuthProvider>
          <LangPartialNote />
          <VerifyNote />
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
          <main className="min-h-0 flex-1 overflow-hidden">
            <AuthGate>{children}</AuthGate>
          </main>
        </AuthProvider>
        </LangProvider>
      </body>
    </html>
  );
}
