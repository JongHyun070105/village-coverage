# Submission Gap Matrix — 2026-10-12

기준 SHA: d93bc31aace96428e38f6f7b1818f40ce36a7e0a
최종 판정: SUBMISSION_PARTIAL

| 항목 | 공식 요구 | 현재 증거 | 판정 | 차단/다음 작업 |
|---|---|---|---|---|
| 성과보고서 | 공식 양식 1부. Word/HWP 최대 2쪽 또는 PPT 약 4쪽 | Markdown 내용 초안, 빈 Word/HWP/PPT 템플릿 복사본. 승인/페이지 증거 없음 | PARTIAL | Q&A 대조 후 완성본 작성, 페이지 수와 사실성 확인, 참가자 승인 |
| 참가신청서 | 참가자 정보와 동의, 대표 1인 자필/전자 서명 | repository에 작성본 없음. 개인정보는 조회/출력하지 않음 | NOT_PRESENT_IN_REPO | 신청자가 저장소 밖에서 작성·서명·동의 확인 |
| 테스트 URL | 웹 솔루션의 실행 URL | web https://villagecoverage-public-demo-web.onrender.com | URL_EXISTS | 제출 자료에 기입. 원격 browser flow 필요 |
| API URL | 일반 사용자 진입점이 아님 | https://villagecoverage-public-demo-api.onrender.com/api/health, 단발 GET 200 | HEALTH_ONLY | API 주소만 제출용 URL로 대체하지 않음 |
| 이전 배포 | 심사 URL의 source provenance | web/API GitHub deployment records success, SHA 7b696499c6c4b59fd613866faa89c1afe8934398 | PREVIOUSLY_DEPLOYED / DEPLOYED_SHA_VERIFIED | 해당 manifest Next 16.3.7. Next 16.3.8은 별도 브랜치 |
| 현재 HTTPS | 저빈도 GET/TLS | web 200/22.685초, API health 200/52.644초 | CURRENT_HTTPS_VERIFIED | 현재 한 시점만 확인. uptime/SLA 증명 아님 |
| 사용자 브라우저 흐름 | 첫 접속과 핵심 기능 접근 | 이 실행에서 원격 브라우저 자동화 없음 | CURRENT_BROWSER_FLOW_VERIFIED=NOT_VERIFIABLE | 제출 직전 fresh browser에서 Dashboard→scenario→decline→replan→memo 확인 |
| 세션·데이터 손실 안내 | 공개 데모 한계 명확화 | 30분 idle expiry 구현; Render Free 임시 파일 시스템과 계획 소실 가능성 배너에 추가 | LOCAL_CHANGE | 갱신한 UI를 local E2E로 검증. 영구 저장 약속 금지 |
| 시연 영상 | 프로토타입 실행화면 2–5분 | repository에 MP4/MOV/WebM 없음 | NOT_PRESENT_IN_REPO | 실제 화면을 녹화하고 길이/음성/개인정보/비밀정보 검사 |
| 아이디어 번호 및 가점 | 수상 아이디어 구현 시 가점 조건; 번호와 관계 확인 | KEIT Q&A 공지 확인, 첨부 답변 본문 다운로드는 WAF 오류 | NOT_VERIFIABLE | 원 제안자/참가자가 답변과 후보작 목록을 대조 |
| 제안자·개발자/IP | 공식 공고상 관계와 IP 확인 | 참가자/권리자의 사실 확인 파일 없음 | USER_CONFIRMATION_REQUIRED | 권리 귀속과 공개 범위를 참가자가 확인 |
| 공식 Q&A/정정 | 최신 공지 검토 | 2026-10-12 사전질의 답변서 notice 게시. Q&A 첨부 내용은 읽지 못함. 확인한 공지 목록에 별도 FAQ는 미확인 | PARTIAL | 원문 접근 가능한 환경에서 문항별 답변 확인. 공고의 추가 조건 반영 |
| 제출 마감 | 2026-10-31 24:00 KST | 공식 기준 문서 및 공고 확인 | STATIC | 내부 목표 2026-10-23 18:00 KST 전 제출물 freeze |

## URL 상태 정의

URL_EXISTS, PREVIOUSLY_DEPLOYED, CURRENT_HTTPS_VERIFIED, CURRENT_BROWSER_FLOW_VERIFIED, DEPLOYED_SHA_VERIFIED, READY_FOR_SUBMISSION은 서로 다른 관측이다. READY_FOR_SUBMISSION은 현재 false이며, 현재 데모 URL은 페이지 전체 흐름 검증을 통과한 것으로 표시하지 않는다.

## 남은 일

1. KEIT Q&A 첨부 원문을 열어 가점·아이디어 번호·권리·제출 파일 세부사항을 확인한다.
2. 성과보고서를 공식 양식과 페이지 제한에 맞게 작성하고, AI/규칙/최적화/통계/합성/사람 결정을 분리해 승인한다.
3. 참가신청서·동의·대표 서명을 저장소 밖에서 작성한다.
4. 공개 URL을 심사자가 사용할 브라우저에서 전 흐름 확인하고 단절·초기화·세션 만료를 기록한다.
5. 2–5분 영상 녹화 및 개인정보/secret/데이터 출처 검토를 한다.
