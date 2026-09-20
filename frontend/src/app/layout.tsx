import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";

import { NavLink } from "@/components/ui";
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
      <body className="flex min-h-full flex-col">
        <header className="sticky top-0 z-20 border-b border-line bg-bg/85 backdrop-blur">
          <nav className="mx-auto flex max-w-7xl items-center gap-1 px-4 py-2.5">
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
          </nav>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-5">{children}</main>
        <footer className="border-t border-line px-4 py-3 text-center text-[11px] text-dim">
          당신은 CEO 입니다. 직원에게 직접 지시하거나 AUTO 로 맡기세요.
        </footer>
      </body>
    </html>
  );
}
