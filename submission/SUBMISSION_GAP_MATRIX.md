# 제출 요건별 현재 상태와 남은 일

공식 근거는 [`docs/SUBMISSION_REQUIREMENTS_2026.md`](../docs/SUBMISSION_REQUIREMENTS_2026.md)를 따른다. 상태는 2026-10-07 기준이다.

| Requirement | Required? | Current state | Evidence | Missing work | Blocker? | Action |
|---|---|---|---|---|---|---|
| 성과보고서 | 필수 | 항목 순서에 맞춘 Markdown 내용 초안 완료, 공식 양식은 미작성 | `성과보고서_내용초안.md`; `forms/original/` | 공식 양식에 옮기고 2쪽 또는 PPT 4쪽 기준으로 편집·검토 | YES | 신청자/아이디어 정보 확인 뒤 Word/HWP/PPT 원본복사본에 작성 |
| 참가신청서 | 필수 | 미작성, 필수 개인정보·동의·서명은 PLACEHOLDER 상태 | 공식 공고 첨부 양식; 요건 감사 문서 | 모든 참가자의 정보, 개인정보 동의 선택, 대표자 서명 | YES | 개인정보가 포함되므로 신청자가 별도 안전한 사본에서 작성 |
| 테스트 URL | 필수 (웹 서비스) | URL 없음. 공개 배포 준비 안 됨 | `DEPLOYMENT_PLAN.md`; `backend/api_feedback.py` | 합성 데이터 전용 모드, 연락처 조회 차단, 공유 쓰기 제한/세션 분리, URL 배포·검증 | **YES — 제출 차단** | 안전 모드 구현과 검증 전에는 외부 공개 금지 |
| 데모 시연 영상 | 필수, 2–5분 | 4분 35초 촬영 대본 작성, 영상 파일 없음 | `DEMO_VIDEO_SCRIPT.md` | 실제 화면 캡처, 대본대로 촬영·편집, 길이·배지·PII 확인 | YES | 안전한 공개 데모가 준비된 뒤 녹화 |
| GitHub 링크/AI 코드·설명 | 선택 | 공개 GitHub 저장소 존재. GitHub API 기준 public, 기본 브랜치 `main`, 라이선스 미표시 | `https://github.com/JongHyun070105/village-coverage`; README | 재현 안내·링크·비밀정보·권리 관계 점검; 공개 라이선스는 권리자 동의 전 추가하지 않음 | NO (선택자료를 낼 경우 확인 필요) | 설명용 링크로만 제시하고 IP/라이선스 확인 |
| 데이터 요약/AI 샘플 | 선택 | 출처 문서와 샘플 산출물은 있으나 제출용 정리본 미작성 | `docs/DATA_PROVENANCE.md`; `docs/MODEL_CARD_DEMAND.md`; `artifacts/` | 실제/공개/외부 사전정보/합성 구분, 재배포 허용 범위 확인 | NO | 선택 제출 시 요약과 비민감 샘플만 구성 |
| 서명 | 필수 | 미기재 | 공식 참가신청서 | 대표자 자필 또는 전자 서명 | YES | 대표자 본인이 서명 |
| 개인정보 동의 | 신청서 내 필수 처리 | 양식에 동의문 포함, 미선택 | 공식 참가신청서 | 모든 참가자의 항목 입력·동의 확인 | YES | 별도 동의서 요구라고 오기하지 말 것 |
| 아이디어 번호/가점 | 조건부 | 공식 후보작 목록에는 이름 `VillageCoverage`만 확인, 번호 없음 | 공식 후보작 목록; `docs/SUBMISSION_REQUIREMENTS_2026.md` | 번호·후보/수상 상태·원 제안자와 개발자 관계·가점 적용 여부 확인 | 제출 내용 정확성을 위한 확인 | `NOT_SPECIFIED`를 임의 번호로 대체하지 않음 |
| 파일 형식/이름 | 필수 형식만 명시 | 공식 파일명 규칙 없음 (`NOT_SPECIFIED`) | 공식 공고·양식 | 제출 형식 선택 후 4개 필수 파일 재생/열기 확인 | NO | 제안 파일명 계획은 내부 일관성 규칙으로만 사용 |
| 마감/이메일 | 필수 | 공식 마감 2026-10-31 24:00, 이메일만 접수 | 공식 공고 | 마감 전 메일 도착과 수신 확인 | YES | 내부 목표 2026-10-23 18:00 KST |
| 이전 서면 질의 답변 대조 | 사용자 요청상 필요 | 답변 원문이 저장소에 없음 | `qa_docx_text.txt`는 빈 공식 양식만 확인됨 | 실제 제출 질문·공개 답변을 개발자/원 제안자가 대조 | YES (본문 최종 승인 전) | 사전 질의 답변 공개 여부를 확인하고 Q&A 기준과 비교 |

## 패키지 예상 구조

실제 개인정보·서명 파일은 저장소 밖에서 관리한다.

```text
VillageCoverage_Submission/
├── 01_참가신청서/PLACEHOLDER_참가신청서.pdf
├── 02_성과보고서/PLACEHOLDER_성과보고서.pdf
├── 03_데모영상/PLACEHOLDER_데모영상.mp4
├── 04_테스트안내/PLACEHOLDER_테스트안내.pdf
└── 05_선택자료/README_GitHub_데이터요약.pdf
```

`PLACEHOLDER` 파일명은 구조 예시이며 최종 파일명은 [`SUBMISSION_CHECKLIST.md`](SUBMISSION_CHECKLIST.md)의 제안안을 참고한다. 공고에는 파일명 규칙이 `NOT_SPECIFIED`다.
