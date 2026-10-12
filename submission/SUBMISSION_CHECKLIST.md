# VillageCoverage 제출 체크리스트

기준일: 2026-10-12 · 내부 제출 목표: 2026-10-23 18:00 KST · 공식 마감: 2026-10-31 24:00 KST

## 현재 공개 데모 상태

- 테스트 웹 URL은 존재하며 현재 HTTPS GET 확인을 통과했다: https://villagecoverage-public-demo-web.onrender.com
- API health URL: https://villagecoverage-public-demo-api.onrender.com/api/health
- 두 GitHub deployment record 모두 success이며 SHA는 7b696499c6c4b59fd613866faa89c1afe8934398, ref는 submission/public-demo-deploy다. 해당 배포 manifest는 Next.js 16.3.7이다.
- web / 와 API /api/health는 2026-10-12 확인 시 HTTP 200, TLS 검증 통과. 응답은 각각 22.685초, 52.644초 걸렸다.
- 현재 HTTPS 연결 확인과 배포 기록 확인은 심사자 브라우저 전체 흐름 확인을 뜻하지 않는다. 원격 browser flow, refresh/deep-link 및 계획 생성~메모 출력은 CURRENT_BROWSER_FLOW_VERIFIED=NOT_VERIFIABLE.
- 보안 후보 Next.js 16.3.8 브랜치는 별도이며 Render에 미배포다.
- 공개 데모는 합성/공개 데이터만 사용한다. Render Free의 재시작·재배포·spin-down 시 임시 계획이 소실될 수 있다. 세션은 30분 idle 뒤 만료된다.
- 최종 판정: SUBMISSION_PARTIAL. URL 확인만으로 제출 준비 완료가 아니다.

## 필수 제출물

| 항목 | 저장소에서 확인한 상태 | 남은 일 |
|---|---|---|
| 성과보고서 | 성과보고서_내용초안.md와 Word/HWP/PPT 빈 템플릿 사본 존재 | 공식 양식에 최종 작성, Word/HWP 최대 2쪽 또는 PPT 약 4쪽, 페이지/수치/표현/승인 확인 |
| 참가신청서 | 참가자 작성본 없음 | 원 제안자·개발자 및 참가자 정보, 필수 동의, 대표 서명 완성. 개인정보와 서명은 이 저장소에 올리지 않음 |
| 테스트 URL | URL_EXISTS, PREVIOUSLY_DEPLOYED, CURRENT_HTTPS_VERIFIED | 신청서/보고서에 web URL 반영 후 별도 fresh-browser flow 확인 |
| 데모 영상 | 저장소에 MP4/MOV/WebM 없음 | 실제 서비스 화면의 2–5분 영상 녹화, 길이·해상도·음성·비밀정보·합성 표시 점검 |
| 아이디어 자격/번호/권리 | 게시된 사전질의 답변 본문 대조 미완료 | 공식 답변 원문 확인 후 후보작 번호, 가점 자격, 원 제안자·개발자 관계, IP 귀속을 신청자가 사실대로 확인 |
| 이메일 접수 | 초안만 존재, 미발송 | 필수 첨부와 제목/수신처를 최종 대조한 뒤 대표자가 직접 발송 |

## 심사 표현 확인

- AI 모델은 비정형 의견을 검토 가능한 초안으로 구조화하는 보조 단계다.
- 충분도/출처/권한 판정은 규칙 처리, 공급 계획은 OR-Tools 제약 최적화, 표본 기반 값은 통계적 추정이다.
- 데모 수요·공급·가격은 합성 시뮬레이션이며 최종 판단과 승인은 사람의 몫이다.
- 현장 예측 정확도, 비용 절감률, 실제 주민 편익은 실증되지 않았다.
- 한 합성 fixture에서 정책 결과가 같아도 네 정책의 일반적인 동등성으로 설명하지 않는다.

## 최신 공식 일정

공식 Q&A 공지는 2026-10-12 게시됐다. 첨부 ZIP은 이 실행에서 KEIT WAF 오류로 다운로드하지 못해 답변 내용은 NOT_VERIFIABLE다. 원 질문과 공식 답변의 조항별 대조 후 보고서를 승인한다.

- [공식 공고](https://www.keit.re.kr/board.es?act=view&bid=0009&list_no=128385&mid=a10301000000&nPage=5)
- [10월 12일 사전질의 답변서 공지](https://www.keit.re.kr/board.es?act=view&bid=0009&list_no=128451&mid=a10301010000&nPage=1)
- 자세한 항목별 증거: [Submission gap matrix](SUBMISSION_GAP_MATRIX.md), [2026 공식 요건](../docs/SUBMISSION_REQUIREMENTS_2026.md)

이 체크리스트는 신청자 작성/승인/서명을 대신하지 않는다. 제출물 완성 전 SUBMISSION_READY를 선언하지 않는다.
