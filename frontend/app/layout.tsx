import type { Metadata } from "next";
import { Sidebar } from "@/components/sidebar";
import { PublicDemoRouteGuard } from "@/components/public-demo-route-guard";
import "./globals.css";

const PUBLIC_DEMO_MODE = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";

export const metadata: Metadata = {
  title: "VillageCoverage | 농촌 생활서비스 공급계획",
  description: "저수요·저데이터 농촌 마을까지 고려하는 생활서비스 공급계획 시뮬레이터",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <div className="app-shell">
          <Sidebar />
          <div className="app-content">
            {PUBLIC_DEMO_MODE ? (
              <aside className="public-demo-banner" aria-label="공개 데모 안내">
                <div>
                  <strong>공개 데모 · 합성/공개 데이터</strong>
                  <p>공모전 체험용 환경입니다. 실제 주민·공급자 운영정보나 행정 승인을 포함하지 않습니다. 이동거리와 계획 결과는 모델 추정입니다. 계획·불참·승인 상태는 브라우저 세션별로 격리되며 30분 동안 활동이 없으면 만료됩니다.</p>
                </div>
                <ol aria-label="추천 체험 순서">
                  <li>미배정 마을 확인</li>
                  <li>4개 공급안 비교</li>
                  <li>데모 불참 후 재계획</li>
                </ol>
              </aside>
            ) : null}
            <PublicDemoRouteGuard>{children}</PublicDemoRouteGuard>
          </div>
        </div>
      </body>
    </html>
  );
}
