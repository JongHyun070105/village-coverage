# Submission evidence update draft — 2026-10-13

This is proposed copy only. The official `submission/final-draft/` package was not modified.

## Public demo verification row

> **공개 데모 브라우저 검증 — 2026.10.13:** 현재 공개 Render URL에서 새 브라우저 A/B를 이용한 합성 사용자 여정을 16개 화면 단계까지 완료했다. 대시보드와 지역 조회, 4개 정책 비교, 계획 재조회, 공급자 참여 화면의 ‘데모 불참’ 버튼, 재계획, 계획 버전, Decision Memo, CSV/PDF 다운로드 및 A/B 데이터 격리를 확인했다. 이 검증 시점의 배포 커밋 SHA와 Render 로그는 확인할 수 없어 수정 후보의 배포 검증이나 최초 계획 재조회 실패의 원인 확인으로 해석하지 않는다.

## AI capability wording

> **생성형 AI:** 비정형 요구 메모를 구조화된 근거 초안으로 바꾸는 Gemini 호출 코드와 Pydantic 스키마를 구현했다. 이번 검증에서는 추가 외부 사용을 만들지 않기 위해 실 Gemini 호출을 수행하지 않았다(`REAL_MODEL_NOT_VERIFIED`). 합성 입력으로 결정적 fallback의 schema 동작은 확인했으나, 예시에서 희망 방문 방식·이동 제약·수요일 제외를 추출하지 못했다. 모델 추출 정확도는 검증되지 않았고 담당자 검토가 필요하다. CP-SAT은 예산·공급·시간 조건을 이용해 계획을 계산하는 별도 최적화 단계다.

## Video guidance

현재 증거만으로는 실제 Gemini 추론 장면을 넣지 않는다. 시연 화면에 구조화 결과를 보여야 한다면 `SYNTHETIC INPUT` 및 `DETERMINISTIC FALLBACK` 표기를 유지하고, 코드 경로 소개와 CP-SAT 분리 설명만 사용한다. 실호출을 확보한 뒤에만 모델명을 표시한 `REAL MODEL INFERENCE` 장면을 추가한다.
