"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, CalendarDays, ChartNoAxesCombined, Compass, FileCheck2, Home, MapPinned, ShieldCheck, Store, Upload, WandSparkles, Scale, MessageSquareText, ClipboardList } from "lucide-react";

const items = [
  { href: "/", label: "공급계획", icon: Home },
  { href: "/pilot-setup", label: "파일럿 초기 설정", icon: ClipboardList },
  { href: "/pilot-imports", label: "파일럿 자료 검토", icon: Upload },
  { href: "/demand", label: "요청 구조화", icon: WandSparkles },
  { href: "/feedback", label: "주민 의견·정정", icon: MessageSquareText },
  { href: "/scenarios", label: "시나리오 비교", icon: Scale },
  { href: "/plans", label: "계획 승인·이력", icon: FileCheck2 },
  { href: "/providers", label: "공급자 참여", icon: Store },
  { href: "/calendar", label: "서비스 일정", icon: CalendarDays },
  { href: "/evidence", label: "근거·출처", icon: Compass },
  { href: "/data-quality", label: "데이터 출처", icon: ShieldCheck },
  { href: "/region-comparison", label: "지역 비교", icon: BarChart3 },
  { href: "/imports", label: "기존 CSV 가져오기", icon: Upload },
  { href: "/methodology", label: "기획 방법", icon: Compass },
];

const PUBLIC_DEMO_MODE = process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE === "true";
const publicDemoPaths = new Set([
  "/",
  "/scenarios",
  "/plans",
  "/providers",
  "/calendar",
  "/evidence",
  "/data-quality",
  "/region-comparison",
  "/methodology",
]);
const visibleItems = PUBLIC_DEMO_MODE ? items.filter((item) => publicDemoPaths.has(item.href)) : items;

export function Sidebar() {
  const pathname = usePathname();
  const pilotDataWorkspace = pathname === "/pilot-setup" || pathname === "/pilot-imports";
  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="VillageCoverage 홈">
        <span className="brand-mark"><MapPinned size={21} strokeWidth={2.2} /></span>
        <span><strong>Village</strong><b>Coverage</b></span>
      </Link>
      <div className="sidebar-section-label">계획</div>
      <nav className="main-nav" aria-label="주요 메뉴">
        {visibleItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link href={href} key={href} className={`nav-link ${active ? "active" : ""}`} aria-current={active ? "page" : undefined}>
              <Icon size={18} strokeWidth={1.9} />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-icon"><ChartNoAxesCombined size={18} /></div>
        <div>
          <strong>{pilotDataWorkspace ? "파일럿 데이터" : "데모 데이터"}</strong>
          <span>{pilotDataWorkspace
            ? "시나리오 가정은 분리 · 미확인 값은 UNKNOWN"
            : "공공자료와 운영값 시뮬레이션을 구분합니다"}</span>
        </div>
        <Activity className="live-dot" size={15} />
      </div>
    </aside>
  );
}
