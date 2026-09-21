import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { LangPartialNote, LangSwitch, Nav } from "@/components/LangSwitch";
import { UserMenu } from "@/components/UserMenu";
import { Icon } from "@/components/icons";
import { LangProvider } from "@/lib/i18n";
import { AuthProvider } from "@/lib/useAuth";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

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
              <span className="ml-auto flex items-center gap-1">
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
