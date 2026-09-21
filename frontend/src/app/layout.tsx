import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { UserMenu } from "@/components/UserMenu";
import { NavLink } from "@/components/ui";
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
      <body className="flex min-h-full flex-col">
        <AuthProvider>
          <header className="sticky top-0 z-20 border-b border-line bg-bg/85 backdrop-blur">
            {/* 좁은 화면에서 메뉴 글자가 두 줄로 쪼개지던 것을 막는다.
                넘치면 접지 말고 옆으로 밀리게 둔다 — 접으면 어떤 메뉴가
                있는지 자체가 안 보인다. */}
            <nav
              className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto
                px-4 py-2.5 [-ms-overflow-style:none] [scrollbar-width:none]
                [&>*]:shrink-0 [&_*]:whitespace-nowrap"
            >
              <Link href="/" className="mr-3 flex items-center gap-2">
                <span className="text-lg" aria-hidden>
                  🏢
                </span>
                <span className="text-sm font-bold tracking-tight">AI COMPANY</span>
              </Link>
              <NavLink href="/">사무실</NavLink>
              <NavLink href="/projects">프로젝트</NavLink>
              <NavLink href="/pricing">요금제</NavLink>
              <NavLink href="/settings">설정</NavLink>
              <UserMenu />
            </nav>
          </header>
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-5">
            <AuthGate>{children}</AuthGate>
          </main>
          <footer className="border-t border-line px-4 py-3 text-center text-[11px] text-dim">
            당신은 CEO 입니다. 직원에게 직접 지시하거나 AUTO 로 맡기세요.
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
