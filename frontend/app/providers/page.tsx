"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, BadgeAlert, Clock3, MapPinned, UsersRound } from "lucide-react";
import { fetchProviders, readSelectedRegionId } from "@/lib/api";
import type { ProviderSummary } from "@/lib/types";

const money = (value: number) => `${value.toLocaleString("ko-KR")}원`;

export default function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderSummary[]>([]);
  const [regionName, setRegionName] = useState("검증 시범 지역");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetchProviders(readSelectedRegionId())
      .then((result) => {
        if (active) {
          setProviders(result.providers);
          setRegionName(result.region);
        }
      })
      .catch((reason: Error) => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, []);

  return (
    <main className="main-content provider-content">
      <header className="topbar"><div className="breadcrumb">공급 운영 <span>/</span> 공급자</div><span className="demo-chip">PRE-R&amp;D 시뮬레이션</span></header>
      <div className="dashboard-content">
        <section className="welcome-row">
          <div><div className="eyebrow"><span className="eyebrow-line" /> PROVIDER DIRECTORY</div><h1>공급자 참여와<br className="mobile-break" /> 회차 기회를 확인합니다</h1><p className="welcome-copy">서비스 역량과 운영 가능 시간을 확인하고, 제공자는 개별 회차 참여 여부를 선택할 수 있습니다.</p></div>
          <div className="region-selector"><span className="region-icon"><MapPinned size={17} /></span><span><small>선택 지역</small><strong>{regionName}</strong></span></div>
        </section>

        <div className="provider-provenance"><BadgeAlert size={17} /><span>공급자, 가용시간, 회차, 보상, 참여 이력은 모두 <b>시연용 합성자료</b>입니다. 실제 사업자나 확정 일정으로 해석하지 마세요.</span></div>

        {error ? <div className="loading-card">공급자 자료를 불러오지 못했습니다. {error}</div> : providers.length === 0 ? <div className="loading-card"><span className="spinner" /> 공급자 자료를 불러오는 중…</div> : (
          <section className="provider-grid" aria-label="공급자 목록">
            {providers.map((provider) => (
              <Link href={`/providers/${provider.provider_id}`} className="provider-card" key={provider.provider_id}>
                <div className="provider-card-head"><span className="provider-avatar"><UsersRound size={20} /></span><span className="provider-demo-label">합성 프로필</span></div>
                <h2>{provider.name}</h2>
                <p className="provider-location"><MapPinned size={14} />{provider.base_location}</p>
                <div className="provider-tags"><span>{provider.service_count}개 서비스</span><span>월 최대 {provider.max_monthly_rounds}회</span></div>
                <div className="provider-summary-grid">
                  <div><small>최대 이동</small><strong><Clock3 size={14} /> {provider.max_travel_time_minutes}분</strong></div>
                  <div><small>최소 보상</small><strong>{money(provider.minimum_compensation_won)}</strong></div>
                </div>
                <span className="provider-open">역량과 참여 회차 보기 <ArrowRight size={15} /></span>
              </Link>
            ))}
          </section>
        )}
        <footer className="page-footer"><span>Provider simulation · 로컬 시연 행위자는 인증되지 않습니다.</span><span>계약·참여 확정은 별도 행정 절차가 필요합니다.</span></footer>
      </div>
    </main>
  );
}
