"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, BadgeAlert, Clock3, MapPinned, Search, UsersRound } from "lucide-react";
import { fetchProviderDirectoryEntries, fetchProviderDirectoryReviews, fetchProviderDirectorySources, fetchProviders, readSelectedRegionId, reviewProviderDuplicate, reviewProviderServiceMapping } from "@/lib/api";
import type { ProviderDirectoryEntry, ProviderDuplicateCandidate, ProviderServiceMappingReview, ProviderSourceRecord, ProviderSummary } from "@/lib/types";

const money = (value: number) => `${value.toLocaleString("ko-KR")}원`;

export default function ProvidersPage() {
  const [providers, setProviders] = useState<ProviderSummary[]>([]);
  const [regionName, setRegionName] = useState("검증 시범 지역");
  const [error, setError] = useState("");
  const [directoryEntries, setDirectoryEntries] = useState<ProviderDirectoryEntry[]>([]);
  const [directorySources, setDirectorySources] = useState<ProviderSourceRecord[]>([]);
  const [directorySearch, setDirectorySearch] = useState("");
  const [directoryOffset, setDirectoryOffset] = useState(0);
  const [directoryError, setDirectoryError] = useState("");
  const [duplicateCandidates, setDuplicateCandidates] = useState<ProviderDuplicateCandidate[]>([]);
  const [mappingReviews, setMappingReviews] = useState<ProviderServiceMappingReview[]>([]);
  const [reviewBusy, setReviewBusy] = useState("");
  const [reviewMessage, setReviewMessage] = useState("");

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
    fetchProviderDirectoryEntries()
      .then((result) => { if (active) setDirectoryEntries(result.entries); })
      .catch((reason: Error) => { if (active) setDirectoryError(reason.message); });
    fetchProviderDirectorySources()
      .then((result) => { if (active) setDirectorySources(result.sources); })
      .catch((reason: Error) => { if (active) setDirectoryError(reason.message); });
    fetchProviderDirectoryReviews()
      .then((result) => {
        if (!active) return;
        setDuplicateCandidates(result.duplicates);
        setMappingReviews(result.mappings);
      })
      .catch((reason: Error) => { if (active) setDirectoryError(reason.message); });
    return () => { active = false; };
  }, []);

  async function searchDirectory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDirectoryError("");
    setDirectoryOffset(0);
    try {
      const result = await fetchProviderDirectoryEntries(directorySearch, 0);
      setDirectoryEntries(result.entries);
    } catch (reason) {
      setDirectoryError(reason instanceof Error ? reason.message : "디렉터리를 검색하지 못했습니다.");
    }
  }

  async function nextDirectoryPage(offset: number) {
    setDirectoryError("");
    try {
      const result = await fetchProviderDirectoryEntries(directorySearch, offset);
      setDirectoryEntries(result.entries);
      setDirectoryOffset(offset);
    } catch (reason) {
      setDirectoryError(reason instanceof Error ? reason.message : "디렉터리 페이지를 불러오지 못했습니다.");
    }
  }

  async function reviewDuplicate(candidateId: string, status: "CONFIRMED_SAME" | "CONFIRMED_DISTINCT") {
    setReviewBusy(candidateId);
    setDirectoryError("");
    try {
      await reviewProviderDuplicate(candidateId, status);
      const result = await fetchProviderDirectoryReviews();
      setDuplicateCandidates(result.duplicates);
      setMappingReviews(result.mappings);
      setReviewMessage("중복 후보 검토를 기록했습니다. 자동 병합은 하지 않았습니다.");
    } catch (reason) {
      setDirectoryError(reason instanceof Error ? reason.message : "중복 검토를 저장하지 못했습니다.");
    } finally {
      setReviewBusy("");
    }
  }

  async function reviewMapping(mappingId: string, status: "VERIFIED_MAPPING" | "REJECTED_MAPPING") {
    setReviewBusy(mappingId);
    setDirectoryError("");
    try {
      await reviewProviderServiceMapping(mappingId, status);
      const result = await fetchProviderDirectoryReviews();
      setDuplicateCandidates(result.duplicates);
      setMappingReviews(result.mappings);
      setReviewMessage("서비스 mapping 검토를 기록했습니다.");
    } catch (reason) {
      setDirectoryError(reason instanceof Error ? reason.message : "서비스 검토를 저장하지 못했습니다.");
    } finally {
      setReviewBusy("");
    }
  }

  return (
    <main className="main-content provider-content">
      <header className="topbar"><div className="breadcrumb">공급 운영 <span>/</span> 공급자</div><span className="demo-chip">현장 검증 전</span></header>
      <div className="dashboard-content">
        <section className="welcome-row">
          <div><div className="eyebrow"><span className="eyebrow-line" /> 공급자 목록</div><h1>공급자 참여와<br className="mobile-break" /> 회차 기회를 확인합니다</h1><p className="welcome-copy">서비스 역량과 운영 가능 시간을 확인하고, 제공자는 개별 회차 참여 여부를 선택할 수 있습니다.</p></div>
          <div className="region-selector"><span className="region-icon"><MapPinned size={17} /></span><span><small>선택 지역</small><strong>{regionName}</strong></span></div>
        </section>

        <div className="provider-provenance"><BadgeAlert size={17} /><span>공급자 프로필·회차·보상·참여 이력은 <b>시연용 합성자료</b>입니다. 날짜별 가용시간을 가져온 경우에만 해당 시간을 CSV로 가져온 운영 입력으로 표시하며, 실제 사업자나 확정 일정으로 해석하지 마세요.</span></div>

        <section className="content-card provider-directory-panel" aria-labelledby="official-directory-heading">
          <div className="provider-directory-head"><div><div className="eyebrow"><span className="eyebrow-line" /> 공식 등록은 운영 확정이 아닙니다</div><h2 id="official-directory-heading">공식 디렉터리 등록 조직</h2></div><span className="provider-real-label">실제 조직 목록</span></div>
          <p>공식 자료에 등재된 조직입니다. 등록은 실제 서비스 제공, 거리상 접근, availability, capacity, price, 참여 의사를 증명하지 않습니다.</p>
          <form className="provider-directory-search" onSubmit={searchDirectory}>
            <label htmlFor="provider-directory-search">조직명·서비스 설명·지역 검색</label>
            <input id="provider-directory-search" value={directorySearch} onChange={(event) => setDirectorySearch(event.target.value)} />
            <button type="submit" className="secondary-button"><Search size={14} /> 검색</button>
          </form>
          <div className="provider-source-list">{directorySources.map((source) => <div key={source.source_id}><a href={source.source_url} target="_blank" rel="noreferrer">{source.source_name}</a><span>{source.ingestion_status} · {source.license_type} · 기준 {source.snapshot_date}</span></div>)}</div>
          {directoryError && <p role="alert">공식 디렉터리를 불러오지 못했습니다. {directoryError}</p>}
          {directoryEntries.length === 0 ? <p>현재 앱 데이터베이스에 공식 디렉터리 행이 없습니다. 담당자가 source 권한과 기준일을 확인한 뒤 <code>uv run python scripts/ingest_provider_directories.py</code>로 승인된 스냅샷을 적재할 수 있습니다.</p> : <div className="provider-directory-list">
            {directoryEntries.map((entry) => <article key={entry.entry_id} className="provider-directory-row">
              <div><span className="provider-real-label">공식 디렉터리</span> <span className="provider-unknown-label">운영조건 미확인</span><h3>{entry.name}</h3><p>{entry.region_label || entry.region_id || "지역정보 없음"} · {entry.organization_type || "유형 미상"}</p></div>
              <div><strong>{entry.public_service_description || entry.service_hint || "서비스 설명 없음"}</strong><span>{entry.mapping_status === "VERIFIED_MAPPING" ? `확인된 서비스 · ${entry.suggested_service_type ?? ""}` : entry.mapping_status === "MAPPING_SUGGESTED" ? "서비스 mapping 후보 · 검토 필요" : "서비스 mapping 확인 필요"}</span></div>
              <div><span>가용성 UNKNOWN</span><span>수용량 UNKNOWN</span><span>가격 UNKNOWN</span></div>
              <small>{entry.source_id} · 기준 {entry.reference_date || "미상"} · {entry.snapshot_id || "snapshot 미연결"}</small>
            </article>)}
            <div className="provider-directory-pagination"><button className="secondary-button" type="button" disabled={directoryOffset === 0} onClick={() => nextDirectoryPage(Math.max(0, directoryOffset - 50))}>이전 50개</button><span>{directoryOffset + 1}–{directoryOffset + directoryEntries.length}개</span><button className="secondary-button" type="button" disabled={directoryEntries.length < 50} onClick={() => nextDirectoryPage(directoryOffset + 50)}>다음 50개</button></div>
          </div>}
        </section>

        <section className="content-card provider-review-panel" aria-labelledby="provider-review-heading">
          <h2 id="provider-review-heading">공급자 중복·서비스 mapping 검토</h2>
          <p>후보는 담당자가 판정합니다. 같은 조직으로 확인해도 레코드는 자동으로 병합하거나 지우지 않습니다.</p>
          {reviewMessage && <p className="import-message" role="status">{reviewMessage}</p>}
          <h3>중복 후보 ({duplicateCandidates.length})</h3>
          {duplicateCandidates.length === 0 ? <p>검토 대기 중인 중복 후보가 없습니다.</p> : duplicateCandidates.map((candidate) => <article className="provider-review-row" key={candidate.candidate_id}>
            <div><strong>{candidate.name_a}</strong><small>{candidate.source_a}</small></div><span aria-hidden="true">↔</span><div><strong>{candidate.name_b}</strong><small>{candidate.source_b}</small></div>
            <div className="provider-review-actions"><button className="secondary-button" type="button" disabled={reviewBusy === candidate.candidate_id} onClick={() => reviewDuplicate(candidate.candidate_id, "CONFIRMED_SAME")}>같은 조직</button><button className="secondary-button" type="button" disabled={reviewBusy === candidate.candidate_id} onClick={() => reviewDuplicate(candidate.candidate_id, "CONFIRMED_DISTINCT")}>별개 조직</button></div>
          </article>)}
          <h3>서비스 분류 ({mappingReviews.length})</h3>
          {mappingReviews.length === 0 ? <p>검토할 서비스 mapping이 없습니다.</p> : mappingReviews.map((mapping) => <article className="provider-review-row" key={mapping.mapping_id}>
            <div><strong>{mapping.organization_name}</strong><small>{mapping.source_id}</small></div><div><strong>{mapping.source_description || "서비스 설명 없음"}</strong><small>{mapping.suggested_service_type || "서비스 연결 없음"} · {mapping.regulation_level} · {mapping.status}</small></div>
            <div className="provider-review-actions"><button className="secondary-button" type="button" disabled={reviewBusy === mapping.mapping_id || !mapping.suggested_service_type || !["UNREGULATED", "LIMITED"].includes(mapping.regulation_level) || mapping.status !== "MAPPING_SUGGESTED"} onClick={() => reviewMapping(mapping.mapping_id, "VERIFIED_MAPPING")}>매핑 확인</button><button className="secondary-button" type="button" disabled={reviewBusy === mapping.mapping_id || !["UNMAPPED", "MAPPING_SUGGESTED"].includes(mapping.status)} onClick={() => reviewMapping(mapping.mapping_id, "REJECTED_MAPPING")}>후보 거절</button></div>
          </article>)}
        </section>

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
