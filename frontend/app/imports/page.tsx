"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { AlertTriangle, Check, Download, FileUp, RotateCcw, ShieldCheck } from "lucide-react";
import {
  approveCSVImportRow,
  fetchImportBatch,
  fetchImportBatches,
  fetchProviders,
  readSelectedRegionId,
  uploadCSVImport,
} from "@/lib/api";
import type { CSVImportBatch, CSVImportRow, CSVImportType, ProviderSummary } from "@/lib/types";

const templates: Record<CSVImportType, { title: string; headers: string[]; description: string }> = {
  demand_observations: {
    title: "수요 관측 기록",
    headers: ["village_code", "date", "service_type", "source_type", "note"],
    description: "법정동 코드별 전화·회의·대리·현장 관측을 등록합니다.",
  },
  provider_availability: {
    title: "공급자 날짜별 가용시간",
    headers: ["provider_id", "date", "start_time", "end_time", "service_type"],
    description: "특정 날짜와 서비스의 가용시간을 등록해 해당 날짜의 주간 시간표를 대체합니다.",
  },
  existing_service_history: {
    title: "기존 서비스 실적",
    headers: ["village_code", "service_type", "program_name", "monthly_rounds", "as_of_date"],
    description: "권역의 기존 월간 제공 회차를 등록합니다. 중앙 신선도 정책상 유효한 실적만 새 계획의 추가 수요에서 차감합니다.",
  },
};

const issueLabels: Record<string, string> = {
  COLUMN_COUNT_MISMATCH: "열 개수가 헤더와 다릅니다.",
  EMPTY_ROW: "빈 행입니다.",
  INVALID_DATE_FORMAT: "날짜는 YYYY-MM-DD 형식이어야 합니다.",
  UNKNOWN_SERVICE_CODE: "등록되지 않은 서비스 코드입니다.",
  SERVICE_NOT_ALLOWED: "초기 지원 범위에서 제외된 서비스입니다.",
  INVALID_LEGAL_CODE_FORMAT: "법정동 코드는 숫자 10자리여야 합니다.",
  LEGAL_CODE_OUTSIDE_ENABLED_PILOTS: "현재 검증된 pilot 권역에 없는 법정동 코드입니다.",
  UNKNOWN_SOURCE_TYPE: "source_type 코드를 확인해 주세요.",
  FUTURE_OBSERVATION_DATE: "관측 날짜가 오늘 이후입니다.",
  PII_REDACTED_REVIEW: "개인정보를 가린 메모를 확인한 뒤 반영해 주세요.",
  PII_IN_PROVIDER_ID: "공급자 ID에 개인정보 형식이 있어 안전하게 등록할 수 없습니다.",
  FIELD_TOO_LONG: "열 값이 허용된 길이를 넘었습니다. CSV를 수정해 다시 올려 주세요.",
  NOTE_REQUIRED: "근거가 되는 조사 메모를 입력해 주세요.",
  DUPLICATE_ROW_IN_FILE: "같은 파일 안에 중복 행이 있습니다.",
  UNKNOWN_PROVIDER_ID: "선택한 지역에 등록된 공급자 ID가 아닙니다.",
  PROVIDER_SERVICE_UNSUPPORTED: "이 공급자는 해당 서비스를 제공하지 않습니다.",
  PAST_AVAILABILITY_DATE: "지난 날짜의 가용시간은 등록할 수 없습니다.",
  INVALID_START_TIME: "시작 시간은 HH:MM 형식이어야 합니다.",
  INVALID_END_TIME: "종료 시간은 HH:MM 형식이어야 합니다.",
  TIME_RANGE_MUST_BE_POSITIVE: "종료 시간은 시작 시간보다 늦어야 합니다.",
  PROGRAM_NAME_REQUIRED: "기존 서비스의 프로그램명을 입력해 주세요.",
  INVALID_MONTHLY_ROUNDS: "월간 제공 회차는 0 이상의 정수여야 합니다.",
  MONTHLY_ROUNDS_OUT_OF_RANGE: "월간 제공 회차는 31회 이하여야 합니다.",
  FUTURE_SERVICE_HISTORY_DATE: "실적 기준일이 오늘 이후입니다.",
  STALE_EXISTING_SERVICE_SNAPSHOT: "중앙 신선도 기준을 넘은 자료입니다. 최신 여부를 확인한 뒤 등록할 수 있습니다.",
};

const statusLabels = {
  IMPORTED: "정상 등록",
  NEEDS_REVIEW: "확인 필요",
  FAILED: "실패",
} as const;

function downloadTemplate(kind: CSVImportType) {
  const csv = `${templates[kind].headers.join(",")}\r\n`;
  const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${kind}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function rowIdentity(batchId: string, rowNumber: number) {
  return `${batchId}:${rowNumber}`;
}

export default function ImportsPage() {
  const [kind, setKind] = useState<CSVImportType>("demand_observations");
  const [file, setFile] = useState<File | null>(null);
  const [batch, setBatch] = useState<CSVImportBatch | null>(null);
  const [providers, setProviders] = useState<ProviderSummary[]>([]);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    fetchProviders(readSelectedRegionId())
      .then((result) => { if (active) setProviders(result.providers); })
      .catch(() => { if (active) setProviders([]); });
    fetchImportBatches()
      .then(async ({ batches }) => {
        if (!active || !batches[0]) return;
        const latest = await fetchImportBatch(batches[0].batch_id);
        if (active) setBatch(latest);
      })
      .catch(() => { if (active) setError("최근 가져오기 이력을 불러오지 못했습니다."); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await uploadCSVImport(kind, await file.arrayBuffer());
      setBatch(result);
      setReviewNotes({});
      setMessage(result.already_imported ? "같은 파일이 이미 처리되어 기존 결과를 불러왔습니다." : "CSV 행별 검증과 저장을 마쳤습니다.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "CSV를 가져오지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  async function approve(row: CSVImportRow) {
    if (!batch) return;
    const key = rowIdentity(batch.batch_id, row.row_number);
    const note = reviewNotes[key] ?? row.record.note ?? "";
    setBusy(true);
    setError("");
    try {
      const updated = await approveCSVImportRow(batch.batch_id, row.row_number, note);
      setBatch(updated);
      setMessage(`CSV ${row.row_number}행을 확인하고 반영했습니다.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "검토 결과를 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page-main">
      <header className="topbar"><div className="breadcrumb"><span>운영 자료</span><span className="breadcrumb-sep">/</span><strong>CSV 가져오기</strong></div><span className="pre-rnd-pill"><i /> 업무 자료</span></header>
      <div className="content-page import-page">
        <div className="content-hero">
          <div className="eyebrow"><span className="eyebrow-line" /> OPERATIONAL DATA IMPORT</div>
          <h1>업무 자료를 검토해 등록합니다</h1>
          <p>행별 성공·확인·실패 이유를 남깁니다. 실패하거나 검토 대기 중인 행은 조용히 버리지 않으며, 같은 파일을 다시 올려도 중복 적용하지 않습니다.</p>
        </div>

        <div className="import-provenance"><AlertTriangle size={17} /><span><b>기존 즉시 반영 경로입니다.</b> 이 페이지는 오류 없는 행을 업로드할 때 반영합니다. 새 파일럿 자료는 먼저 <Link href="/pilot-imports">미리보기·검토·확정 workflow</Link>를 사용하세요.</span></div>

        <div className="import-provenance"><ShieldCheck size={17} /><span>등록된 자료는 <b>가져온 업무 자료</b>로 구분합니다. 수요 메모의 전화번호 등 식별 정보는 저장 전에 가리며, 검토 대기 행은 승인 전까지 근거에 반영하지 않습니다.</span></div>

        <section className="content-card import-card">
          <div className="import-tabs" role="tablist" aria-label="CSV 종류">
            {(Object.keys(templates) as CSVImportType[]).map((item) => (
              <button key={item} type="button" role="tab" aria-selected={kind === item} className={kind === item ? "active" : ""} onClick={() => { setKind(item); setFile(null); }}>
                {templates[item].title}
              </button>
            ))}
          </div>
          <div className="import-description">
            <div><h2>{templates[kind].title}</h2><p>{templates[kind].description}</p></div>
            <button className="secondary-button" type="button" onClick={() => downloadTemplate(kind)}><Download size={15} /> CSV 양식</button>
          </div>
          <div className="import-schema">
            <strong>필수 열</strong><code>{templates[kind].headers.join(",")}</code>
            <strong>서비스 코드</strong><code>laundry · daily_necessities · home_repair</code>
            {kind === "demand_observations" ? <><strong>source_type</strong><code>phone · village_meeting · proxy · field</code></> : kind === "provider_availability" ? <><strong>등록 공급자</strong><span>{providers.length ? providers.map((provider) => <code key={provider.provider_id}>{provider.provider_id}</code>) : "선택 지역 공급자 목록을 불러오지 못했습니다."}</span><strong>날짜별 동작</strong><span>등록한 날짜에는 해당 공급자 주간 시간표 대신 CSV 시간을 적용합니다.</span></> : <><strong>자료 기준</strong><span>프로그램별 최신 스냅샷을 저장하고, 중앙 신선도 정책상 유효한 자료만 계획에서 기존 제공 회차로 셉니다.</span><strong>수요 계산</strong><span>합성 월간 기준수요에서 확인된 기존 회차를 빼고 추가 제공량을 최적화합니다. 기록이 없거나 오래된 경우 수요는 줄이지 않습니다.</span></>}
          </div>
          <form className="import-form" onSubmit={submit}>
            <label htmlFor="csv-file">UTF-8 또는 CP949 CSV 파일</label>
            <input id="csv-file" type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            <button className="primary-button" type="submit" disabled={!file || busy}><FileUp size={16} />{busy ? "검증·저장 중…" : "검증하고 가져오기"}</button>
          </form>
          {message && <p className="import-message" role="status"><Check size={16} />{message}</p>}
          {error && <div className="alert-box" role="alert"><AlertTriangle size={16} />{error}</div>}
        </section>

        {batch && <section className="content-card import-results" aria-label="가져오기 결과">
          <div className="import-results-head"><div><span className="eyebrow">IMPORT BATCH · {batch.batch_id.slice(0, 8)}</span><h2>{templates[batch.import_type].title}</h2></div><button type="button" className="text-button" onClick={() => fetchImportBatch(batch.batch_id).then(setBatch).catch((reason: Error) => setError(reason.message))}><RotateCcw size={14} /> 새로고침</button></div>
          <div className="quality-grid import-counts">
            <div className="quality-stat"><span>총 행</span><strong>{batch.total_rows}<small>행</small></strong></div>
            <div className="quality-stat"><span>정상 등록</span><strong>{batch.valid_rows}<small>행</small></strong></div>
            <div className="quality-stat review-count"><span>확인 필요</span><strong>{batch.needs_review_rows}<small>행</small></strong></div>
            <div className="quality-stat failed-count"><span>실패</span><strong>{batch.failed_rows}<small>행</small></strong></div>
          </div>
          <div className="import-row-list">
            {(batch.rows ?? []).map((row) => {
              const key = rowIdentity(batch.batch_id, row.row_number);
              const note = reviewNotes[key] ?? row.record.note ?? "";
              return <article className={`import-row ${row.status.toLowerCase()}`} key={row.row_id}>
                <div className="import-row-head"><strong>CSV {row.row_number}행</strong><span className={`import-status ${row.status.toLowerCase()}`}>{statusLabels[row.status]}</span></div>
                <div className="import-row-values">{Object.entries(row.record).filter(([field]) => field !== "note").map(([field, value]) => <span key={field}><b>{field}</b> {value || "(빈 값)"}</span>)}</div>
                {row.record.note !== undefined && <p className="import-note-preview">메모: {row.record.note || "(입력 없음)"}{row.redacted && <small> · 개인정보 가림</small>}</p>}
                {row.status === "NEEDS_REVIEW" && <div className="import-review">{row.record.note !== undefined && <><label htmlFor={`review-${row.row_id}`}>확인할 메모</label><textarea id={`review-${row.row_id}`} rows={2} maxLength={3000} value={note} onChange={(event) => setReviewNotes((current) => ({ ...current, [key]: event.target.value }))} /></>}<button type="button" className="secondary-button" disabled={busy || (row.record.note !== undefined && !note.trim())} onClick={() => approve(row)}><Check size={14} /> 확인 후 반영</button></div>}
                {row.issues.length > 0 && <ul className="import-issues">{row.issues.map((issue) => <li key={issue}>{issueLabels[issue] ?? issue}</li>)}</ul>}
              </article>;
            })}
          </div>
        </section>}
        <footer className="provenance-footer">가져온 업무 자료는 공개자료와 시뮬레이션에 합쳐 표시하지 않고, 각 기록의 출처를 구분해 유지합니다.</footer>
      </div>
    </main>
  );
}
