# VillageCoverage KEIT 제출 초안 상태

## 2026-10-24 20시 재개 검증

동결 실행 소스 `9a8c4bed60bca57cce2941a028945b2f002c6f01`의 [CI 40073124556](https://github.com/JongHyun070105/village-coverage/actions/runs/40073124556)가 전체 성공했다. SECURITY_PASS / FULL_REGRESSION_PASS는 해당 RC 소스 범위다. 원격 endpoint 5개는 단발 조회에서 200이었으나 Render 현재 SHA·추적 branch·rollback·최종 UI 시연은 여전히 NOT_VERIFIABLE이다. 후보 배포는 NOT_DEPLOYED, 제출 준비는 PARTIAL이며 동결 완료로 표시하지 않는다. Office/영상은 미검증·미제작, Gemini는 REAL_MODEL_NOT_VERIFIED를 유지한다. 아래 기존 작성 기록은 당시 범위이며 최신 근거는 `docs/FINAL_RELEASE_AUDIT_20261024.md`를 우선한다.


## 2026-10-24 최종 RC 갱신

- 통합 브랜치: `security/final-release-20261024`, 실행 코드 SHA `9a8c4bed60bca57cce2941a028945b2f002c6f01`. PR #1·#2·공식 제출 패키지 원본 이력을 모두 보존했다.
- Next.js·eslint-config-next 16.4.3, React·React DOM 19.2.9. 전체/Production npm audit 0건, Node 22 standalone build 확인. Python 운영 감사에서 발견한 3종 39개 권고도 certifi 2026.10.23·OpenTelemetry API 1.45.1·Pillow 13.0.0으로 보안 갱신해 알려진 권고 0건으로 재검사했다. 전체 회귀와 exact-SHA GitHub CI의 최종 결과는 `docs/FINAL_RELEASE_AUDIT_20261024.md`와 `artifacts/qa/final_full_regression_20261024.json`을 따른다.
- 이번 실행에서 신규 Render 배포를 하지 않았다. 현재 이미지 SHA·추적 브랜치·retained-artifact rollback은 접근 도구 부재로 NOT_VERIFIABLE이다. 기존 서비스 단발 응답과 과거 성공 배포 기록을 최신 RC 배포 증거로 사용하지 않는다.
- 로컬 Chromium에서 실제 `데모 불참` 클릭, v2 재계획, 세 브라우저 세션 격리, PDF/CSV 흐름을 실행했다. 원격 최신 RC의 16단계와 4개 뷰포트는 미실행이며 새 원격 캡처는 없다.
- PPTX·DOCX·공식 빈 양식·기존 이미지/미리보기 PDF는 바이트 단위로 보존했다. PPT 4장은 STATIC 확인했다. Word 실제 2쪽 이하·PPT 3장 숫자/구분선·폰트·잘림의 Office 렌더는 NOT_VERIFIABLE이다. 기존 QA 미리보기를 Office 출력으로 표현하지 않는다.
- Gemini: `REAL_MODEL_NOT_VERIFIED`. 영상: `VIDEO_NOT_RENDERED`. 참가자 정보·동의·날짜·서명·IP·가점은 USER_CONFIRMATION_REQUIRED이며 공개 저장소에 입력하지 않았다. 이메일은 보내지 않았다.
- 판정: 제출 기술 준비 PARTIAL, 공개 데모 릴리스 NO-GO. 기존 조건부 GO의 기술 게이트가 충족되면 기존 권한 범위에서 재개할 수 있다.

이하 2026-10-13 내용은 당시 작성 기록이며 현재 판정은 위 갱신과 최종 감사 문서를 우선한다.

기준: 2026-10-13 · 독립 작업 worktree · 기준 브랜치 `security/release-readiness-20261012` (`b6ff52adb2fa8b4287e6c62250802d8c07196907`)
상태 정의: EXEC PASS=직접 실행 확인 · STATIC=파일/코드 구조 확인 · SKIP=수행하지 않음 · NOT_VERIFIABLE=현재 도구/접근으로 확인 못함 · USER_CONFIRMATION_REQUIRED=참가자/권리 당사자 확인 필요.

## A. 공식 요건

- **EXEC PASS** — KEIT 공식 산업통상부 공고 제2026-614호 원문 PDF와 첨부 양식을 확인·보존했다. 마감은 2026-10-31 24:00, 접수 주소는 `relations2@keit.re.kr`; 성과보고서, 참가신청서, 웹 테스트 URL, 2–5분 데모 영상이 요구된다.
- **STATIC** — 성과보고서는 HWP/Word/PPT/PDF 허용 형식, Word/HWP는 최대 2쪽, PPT는 4쪽 내외이며 항목 순서를 유지한다. 팀 신청은 참가자 전원의 정보/동의와 대표자 서명이 필요하다.
- **STATIC** — 공식 성과보고서 ZIP에는 HWP·Word·PPT가, 별도 참가신청 ZIP에는 HWP·Word 양식이 있다. 원본은 `submission/forms/original/`, 복사본은 `submission/forms/draft/`에 보존했다.
- **USER_CONFIRMATION_REQUIRED** — VillageCoverage는 공식 PDF의 `수상 후보작 목록`에 등재된 사실까지만 확인됐다. 과거 대회 입상 확정, 아이디어 번호, 5점 가점 적용 자격은 확인되지 않았다.
- **USER_CONFIRMATION_REQUIRED** — 공고에 입상 아이디어 기반 산출물의 제안자·개발자 간 50:50 공동소유 원칙이 있다. 실제 제안자/개발자 동일인 여부, 참가 팀과 IP 귀속, 출원·공개 가능 범위, 중복 제출 진술은 당사자 확인이 필요하다.
- 2026-10-12 사전질의 답변은 사용자가 이전 질문에 직접 작성한 제안 취지 설명으로 귀속했다. **KEIT가 VillageCoverage의 개별 기술·가중치·가격·구현을 승인했다는 뜻으로 사용하지 않았다.**

## B. 산출물

- **STATIC / 4 slides** — `VillageCoverage_성과보고서_20261023.pptx`: 공식 4장 PPTX를 복제해 제작. 기존 로고/헤더/페이지 번호/작성 안내와 공식 항목 제목을 보존했고, 첫 제목은 요청대로 `1. AI 기술명`으로 표시했다.
- **STATIC / 목표 2쪽** — `VillageCoverage_성과보고서_20261023.docx`: 공식 Word 양식 기반. 보고서 7개 항목 순서 및 원래 참가/아이디어/개발내용 안내 문구를 보존하고, 배포 DOCX에 함께 있던 참가신청서 표만 보고서 작업본에서 분리했다.
- **EXEC PASS / preview pages rendered and viewed** — `VillageCoverage_성과보고서_20261023_PPTX_검증미리보기.pdf` (4쪽)와 `VillageCoverage_성과보고서_20261023_DOCX_검증미리보기.pdf` (2쪽)는 같은 내용으로 만든 **검증 미리보기**다. 실제 PowerPoint/Word에서 변환한 PDF가 아니다. 이 PDF를 최종 제출 PDF로 사용하지 말고, Office/LibreOffice에서 원본 파일을 열어 변환·페이지 수·시각 검사를 다시 해야 한다.
- **NOT_VERIFIABLE** — 시스템에 PowerPoint/Word/LibreOffice 변환기가 없어 PPTX와 DOCX의 네이티브 렌더링, 실제 Word 페이지 수·페이지 분할, 폰트 대체·인쇄 잘림은 확인하지 못했다. 미리보기 PNG는 각각 `evidence/rendered/ppt-slide-*.png`, `evidence/rendered/docx-page-*.png`이다.
- **EXEC PASS / capture provenance** — `evidence/source/`는 격리 로컬 Playwright 실행에서 직접 캡처한 화면의 원본이다. PPT 내 이미지는 해당 화면 crop이며 합성 UI를 새로 그리지 않았다. 모든 캡처는 synthetic demo DB를 사용하고 원격 Render 배포본이 아니다.

## C. 내용 품질

- 문제 정의는 요청 기록 부족을 실제 필요 부족으로 오인할 위험으로 표현했다.
- AI 역할은 근거 정리/구조화 보조, 불확실성 관리, CP-SAT 제약 최적화로 나눴다. 예산·정책 결정을 AI가 직접 한다고 쓰지 않았다.
- 정확한 통제 실험은 `experiment_1_request_count_vs_balanced`만 인용: 홍성군 장곡면, 16개 권역, 5,000,000원, 합성 관측 4건 미만을 조사 필요로 둔 조건에서 두 정책 모두 19단위; 권역 배정 3/16 대 12/16; 조사 필요 권역 배정 0/8 대 7/8. 모든 수치에 `SIMULATED FOR PRE-R&D`를 붙였다.
- 모델 이동비는 실제 집행비가 아님을 표시했다. 위 두 정책 실험을 네 정책 UI 비교와 분리했다.
- 실제 코드 매핑·근거·가정·한계·안전 문구는 `CLAIM_VERIFICATION.md`에 기록했다. 공개 E2E에서 Gemini 호출/예측 정확도는 확인하지 않았다.
- **STATIC** — 원 제안 취지(간단 집수리, 낮은 요청 기록과 낮은 수요의 구분, 최소 서비스 기회, 비용 항목 구분, 제공자 불참 재계획, 사람 결정)와 시제품 구현 선택을 분리했다. 제안 당시 미확정이던 가중치·가격을 확정된 원안처럼 쓰지 않았다.

## D. 영상

- **STATIC** — `DEMO_FINAL_SCRIPT.md`에 4:35 타임코드, 나레이션, 화면 동작, 대기 기준, 자막, 허용 수치, 합성/실증 고지 및 일치 감사 항목을 작성했다.
- **EXEC PASS** — `DEMO_RECORDING_CHECKLIST.md`, `JUDGE_DEMO_GUIDE.md`에 실제 촬영 전 확인할 화면·보안·데이터 조건을 정리했다.
- **VIDEO_NOT_RENDERED** — 영상/음성 파일은 생성하지 않았다. 현 도구에는 녹음·나레이션·편집 경로가 없고, 공개 원격 데모가 데이터 오류를 보여 촬영 가능한 심사 URL로 확인되지 않았다.
- **NOT_VERIFIABLE** — 대본의 UI 클릭별 촬영 경로는 원격 화면에서 재현하지 못했다. 특히 현재 로컬 E2E는 제공자 불참을 API로 입력했으므로 영상 촬영 전 화면의 `데모 불참` 버튼 경로를 별도로 확인해야 한다.

## E. 제출 준비

- 성과보고서: **초안 파일 완성**. 네이티브 Office 렌더와 최종 PDF 변환은 보류.
- 신청서: **USER_CONFIRMATION_REQUIRED** — 빈 공식 DOCX/HWP 사본만 준비. 개인 정보, 동의 선택, 날짜, 서명은 채우지 않았다.
- 웹 테스트 URL: `https://villagecoverage-public-demo-web.onrender.com` — **NOT_VERIFIABLE**. 2026-10-13 원격 브라우저는 cold start 뒤 UI가 열렸지만 계획 데이터 재조회가 실패했고 재시도 뒤 같은 오류가 다시 표시됐다. Dashboard 외 경로는 진행하지 않았다.
- 영상: **VIDEO_NOT_RENDERED**. 실제 촬영/편집 필요.
- 후보 자격/아이디어 번호/IP: **USER_CONFIRMATION_REQUIRED**.
- 발송: **SKIP** — 대회 이메일을 보내지 않았다.
- 내부 목표일 2026-10-23 18:00 KST, 공식 마감 2026-10-31 24:00 KST. 제출 직전에 2026-10-14 예정 Next.js 보안 업데이트 반영 여부, 새 배포 SHA, Render URL을 다시 점검한다.

## F. Git 및 검증

- 기준: `security/release-readiness-20261012` at `b6ff52adb2fa8b4287e6c62250802d8c07196907`.
- 작업: `submission/official-package-20261013`의 독립 worktree `.codex-official-submission`.
- **EXEC PASS** — `frontend/e2e/public-sector-workflow.spec.ts` 1건 통과. 실제 로컬 앱/Playwright에서 네 정책 비교, 계획 세부·불참 반영 새 버전, PDF/CSV export 경로를 확인했다. 외부 Gemini 키 없이 격리된 임시 DB로 실행했다.
- **EXEC PASS** — 미리보기 PPT 4쪽과 Word 2쪽의 raster 화면을 모두 열어 확인했고, 공개 패키지 38개 파일의 manifest SHA/바이트 수를 대조했다. Word 작업본의 공식 항목·안내 문구 보존, 참가신청서 DOCX/HWP의 공식 빈 복사본과 해시 일치, 보고서의 참가신청서 표 분리도 확인했다. 단순 전화번호·secret 패턴 검사는 0건이다.
- **NOT_VERIFIABLE** — 위 화면은 직접 만든 QA raster 미리보기이며 PowerPoint/Word 렌더 결과가 아니다. Native Office 페이지 나눔·글꼴 대체·PDF 내보내기는 별도 확인해야 한다.
- **NOT_VERIFIABLE** — 최종 독립 교차검토 배치는 한 Gemini reviewer만 시작됐고 `AUTHORITATIVE_MAIN_CHECKOUT_CHANGED_DURING_DELEGATE` guard로 수집 결과 `BLOCKED`/usable worker 0이다. reviewer 요약은 무발견이었지만 독립 PASS로 채택하지 않았다. 이전 AGY Sonnet 호출도 rate limit으로 유효 결과가 없어 2-provider consensus는 확보되지 않았다. 주요 양식·수치는 MAIN이 직접 재대조했다.
- 공개 Render 사용자 데이터 변경이나 배포는 없었다. 메인 작업트리의 기존 dirty/untracked 파일과 다른 worktree를 수정하지 않았다.
- 최종 산출물 SHA/바이트 수는 `PACKAGE_MANIFEST.md`에 기록한다.
- **EXEC PASS** — 제출 브랜치 패키지를 일반 push했고, 원격 ref가 push 직후 로컬 HEAD와 일치함을 확인했다. 이 상태/manifest 갱신도 같은 브랜치에 push한 뒤 최종 SHA를 다시 대조한다. 기존 Draft PR #1은 열어두며 병합하지 않는다.

재생성 명령(현재 작성 호스트): `uv run --isolated --with python-docx --with python-pptx --with pillow python submission/final-draft/build_submission_package.py`. 생성된 `*_검증미리보기.pdf`는 QA 전용이다.

## 제출 전 필수 사용자 확인

1. 공식 아이디어 번호, 과거 대회 정확한 선정/입상 상태, 5점 가점 적용 여부.
2. 참가자 전체 정보/대표자, 개인정보 동의, 날짜, 서명.
3. 원 제안자·개발자 관계, 50:50 IP 적용 여부, 출원 및 공개 범위.
4. 원격 demo가 최신 기대 SHA로 정상인지, 공개 브라우저에서 전체 경로가 재현되는지.
5. 실제 Office에서 DOCX 2쪽 이하/PPTX 4장 렌더와 네이티브 PDF 내보내기, 2–5분 영상 촬영·검수.
