"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AlertTriangle, Check, ChevronLeft, ChevronRight, Download, FileUp, ShieldCheck } from "lucide-react";
import {
  confirmPilotImport,
  downloadPilotImportErrors,
  fetchPilotImportTemplates,
  previewPilotImport,
  type PilotImportBatch,
  type PilotImportTemplates,
} from "@/lib/api";

const PAGE_SIZE = 50;
const sourceLabels: Record<string, string> = {
  PUBLIC_DATA: "공공데이터",
  OFFICIAL_DIRECTORY: "공식 디렉터리",
  LOCAL_AUTHORITY_INPUT: "지자체 입력",
  SURVEY_INPUT: "주민 조사",
  PROVIDER_SELF_REPORTED: "공급자 자가보고",
  SERVICE_EXECUTION_LOG: "수행로그",
  RESIDENT_FEEDBACK: "주민 의견",
  SIMULATED: "모의값",
};

export default function PilotImportsPage() {
  const [manifest, setManifest] = useState<PilotImportTemplates | null>(null);
  const [kind, setKind] = useState("");
  const [sourceType, setSourceType] = useState("LOCAL_AUTHORITY_INPUT");
  const [file, setFile] = useState<File | null>(null);
  const [batch, setBatch] = useState<PilotImportBatch | null>(null);
  const [confirmedByUser, setConfirmedByUser] = useState(false);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    fetchPilotImportTemplates()
      .then((result) => {
        setManifest(result);
        setKind(Object.keys(result.templates)[0] ?? "");
      })
      .catch((cause: Error) => setError(cause.message));
  }, []);

  const template = manifest?.templates[kind];
  const pageCount = Math.max(1, Math.ceil((batch?.rows.length ?? 0) / PAGE_SIZE));
  const rows = useMemo(
    () => batch?.rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE) ?? [],
    [batch, page],
  );

  async function createPreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !kind) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await previewPilotImport(kind, file.name, await file.arrayBuffer(), sourceType);
      setBatch(result);
      setConfirmedByUser(false);
      setPage(0);
      setMessage(result.already_exists ? "같은 파일의 기존 batch 미리보기를 불러왔습니다." : "미리보기와 행별 검증을 만들었습니다. 아직 운영 자료로 확정하지 않았습니다.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "CSV를 읽지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmImport() {
    if (!batch || !confirmedByUser || batch.status !== "PREVIEWED") return;
    setBusy(true);
    setError("");
    try {
      const result = await confirmPilotImport(batch.batch_id);
      setBatch(result);
      setMessage(`${result.rows_imported}개 행을 확인된 파일럿 입력으로 저장했습니다. 오류 ${result.rows_error}개는 제외했고 기록은 유지됩니다.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "자료를 확정하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page-main">
      <header className="topbar">
        <div className="breadcrumb"><Link href="/pilot-setup">파일럿 초기 설정</Link><span className="breadcrumb-sep">/</span><strong>자료 미리보기</strong></div>
        <span className="pre-rnd-pill"><i /> PILOT DATA INTAKE</span>
      </header>
      <div className="content-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> PREVIEW · VALIDATE · CONFIRM</div>
          <h1>자료를 검토한 뒤 가져옵니다</h1>
          <p>업로드만으로 계획 데이터에 반영하지 않습니다. 오류와 경고를 검토하고 명시적으로 확정해야 저장됩니다.</p>
        </div>
        <div className="import-provenance"><ShieldCheck size={17} /><span>파일럿 입력은 현재 데모 최적화기에 자동 합쳐지지 않습니다. 등록된 조직은 실제 운영 가능성을 뜻하지 않으며, `SIMULATED` 자료는 실제값으로 승격되지 않습니다.</span></div>

        <section className="content-card">
          <h2>1. 양식과 출처 선택</h2>
          {!manifest && !error && <p role="status">CSV 양식을 불러오는 중입니다.</p>}
          {template && manifest && <form className="import-form pilot-import-form" onSubmit={createPreview}>
            <label htmlFor="pilot-template">CSV 양식</label>
            <select id="pilot-template" value={kind} onChange={(event) => { setKind(event.target.value); setBatch(null); setFile(null); }}>
              {Object.keys(manifest.templates).map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
            <label htmlFor="pilot-source">기본 출처 유형</label>
            <select id="pilot-source" value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
              {manifest.source_types.map((value) => <option key={value} value={value}>{sourceLabels[value] ?? value}</option>)}
            </select>
            <a className="secondary-button" href={`/templates/${template.filename}`} download><Download size={15} /> CSV 양식 다운로드</a>
            <p className="pilot-import-hint">필수 열 {Object.entries(template.fields).filter(([, field]) => field.required).map(([name]) => name).join(", ")}</p>
            <a className="text-link" href="#pilot-field-reference">필드 정의·PII·출처 안내 보기</a>
            <label htmlFor="pilot-csv-file">UTF-8 또는 CP949 CSV 파일</label>
            <input id="pilot-csv-file" type="file" accept=".csv,text/csv" required onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            <button className="primary-button" type="submit" disabled={!file || busy}>{busy ? "행을 검증하는 중…" : <><FileUp size={16} /> 미리보기 만들기</>}</button>
          </form>}
          {message && <p className="import-message" role="status"><Check size={16} />{message}</p>}
          {error && <div className="alert-box" role="alert"><AlertTriangle size={16} />{error}</div>}
        </section>

        {template && <section className="content-card" id="pilot-field-reference" aria-label="선택한 CSV 필드 설명">
          <h2>{kind} 필드 안내</h2>
          <div className="table-wrap"><table className="data-table"><caption>{kind} CSV의 형식, 필수 여부, 예시와 개인정보 위험</caption>
            <thead><tr><th scope="col">필드</th><th scope="col">형식</th><th scope="col">필수</th><th scope="col">예시</th><th scope="col">설명·PII 위험·출처 해석</th></tr></thead>
            <tbody>{Object.entries(template.fields).map(([name, field]) => <tr key={name}><th scope="row">{name}</th><td>{field.type}</td><td>{field.required ? "필수" : "선택"}</td><td>{field.example}</td><td>{field.description} · 개인정보 위험: {field.pii_risk} · {field.provenance_interpretation}</td></tr>)}</tbody>
          </table></div>
        </section>}

        {batch && <section className="content-card" aria-label="가져오기 미리보기">
          <div className="import-results-head"><div><span className="eyebrow">BATCH · {batch.batch_id.slice(0, 8)}</span><h2>{batch.file_name}</h2></div><span className="import-status">{batch.status === "PREVIEWED" ? "확정 전 미리보기" : "확정됨"}</span></div>
          <div className="quality-grid import-counts">
            <div className="quality-stat"><span>전체 행</span><strong>{batch.rows_total}<small>행</small></strong></div>
            <div className="quality-stat"><span>오류 없음</span><strong>{batch.rows_valid}<small>행</small></strong></div>
            <div className="quality-stat review-count"><span>경고 검토</span><strong>{batch.rows_warning}<small>행</small></strong></div>
            <div className="quality-stat failed-count"><span>가져오기 불가</span><strong>{batch.rows_error}<small>행</small></strong></div>
          </div>
          <div className="pilot-import-actions">
            {batch.rows_error > 0 && <button type="button" className="secondary-button" onClick={() => downloadPilotImportErrors(batch.batch_id).catch((cause: Error) => setError(cause.message))}><Download size={15} /> 실패 행 다운로드</button>}
            <span>표시 {batch.rows.length === 0 ? 0 : page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, batch.rows.length)} / {batch.rows_total}</span>
            <button type="button" className="secondary-button" disabled={page === 0} aria-label="이전 50행" onClick={() => setPage((value) => Math.max(0, value - 1))}><ChevronLeft size={16} /> 이전</button>
            <span>페이지 {page + 1} / {pageCount}</span>
            <button type="button" className="secondary-button" disabled={page + 1 >= pageCount} aria-label="다음 50행" onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}>다음 <ChevronRight size={16} /></button>
          </div>
          <div className="pilot-preview-list">
            {rows.map((row) => <article className="pilot-preview-row" key={`${batch.batch_id}-${row.row_number}`}>
              <div className="import-row-head"><strong>CSV {row.row_number}행</strong><span className={`import-status ${row.status.toLowerCase()}`}>{row.status === "VALID" ? "오류 없음" : row.status === "WARNING" ? "확인 필요" : "가져오기 불가"}</span></div>
              <dl>{Object.entries(row.normalized_record).map(([field, value]) => <div key={field}><dt>{field}</dt><dd>{value || "(빈 값)"}</dd></div>)}</dl>
              {row.issues.length > 0 && <ul className="import-issues">{row.issues.map((issue, index) => <li key={`${issue.code}-${index}`}><strong>{issue.severity}</strong> · {issue.detail}</li>)}</ul>}
            </article>)}
          </div>
          {batch.status === "PREVIEWED" && <div className="pilot-import-confirm">
            <label><input type="checkbox" checked={confirmedByUser} onChange={(event) => setConfirmedByUser(event.target.checked)} /> 오류·경고·출처를 확인했으며, 경고 행을 검토 후 가져오도록 확정합니다.</label>
            <button className="primary-button" type="button" disabled={!confirmedByUser || busy || batch.rows_valid + batch.rows_warning === 0} onClick={confirmImport}>확인한 행 가져오기</button>
          </div>}
          {batch.status !== "PREVIEWED" && <p className="import-message" role="status">확정 입력 {batch.rows_imported}행 · 오류 제외 {batch.rows_error}행</p>}
        </section>}
        <p className="provenance-footer">개인 연락처·이름·상세 주민 주소·민감정보를 CSV에 넣지 마십시오. 텍스트 가림은 보조 장치이며 개인정보 완전 탐지 기능이 아닙니다. 전체 필드별 설명은 저장소의 <code>docs/LOCAL_DATA_IMPORT_GUIDE.md</code>에 있습니다.</p>
      </div>
    </main>
  );
}
