"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const PUBLIC_DEMO_MODE = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";
const RESTRICTED_PATHS = ["/demand", "/feedback", "/imports", "/pilot-imports", "/pilot-setup"];

export function PublicDemoRouteGuard({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const restricted = PUBLIC_DEMO_MODE && RESTRICTED_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );

  if (restricted) {
    return (
      <main className="page-main content-page" role="alert" aria-label="공개 데모 경로 제한">
        <section className="content-card public-demo-restricted-page">
          <div className="eyebrow">PUBLIC DEMO · RESTRICTED</div>
          <h1>이 기능은 공개 데모에서 사용할 수 없습니다</h1>
          <p>주민 조사·연락처·파일럿 자료 입력은 공개 데모에서 비활성화되어 있습니다. 합성 데이터를 이용한 계획 비교와 재계획은 Dashboard에서 체험할 수 있습니다.</p>
          <Link href="/" className="button button-dark">공개 데모로 돌아가기</Link>
        </section>
      </main>
    );
  }

  return children;
}
