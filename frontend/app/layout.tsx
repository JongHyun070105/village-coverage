import type { Metadata } from "next";
import { Sidebar } from "@/components/sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "VillageCoverage | 농촌 생활서비스 공급계획",
  description: "저수요·저데이터 농촌 마을까지 고려하는 생활서비스 공급계획 시뮬레이터",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body><div className="app-shell"><Sidebar />{children}</div></body>
    </html>
  );
}
