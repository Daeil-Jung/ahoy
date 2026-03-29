# Adversarial Review (alecnielsen/adversarial-review) 분석 리포트

> 분석일: 2026-03-28 (8차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Adversarial Review |
| GitHub URL | https://github.com/alecnielsen/adversarial-review |
| 스타 | 4 |
| 최근 커밋 | 2026-01-22 |
| 라이선스 | MIT |
| 언어 | Shell (Bash) |
| 핵심 키워드 | 4단계 적대적 토론, Claude+Codex 교차 리뷰, 서킷 브레이커, 컨센서스 빌딩 |

## 핵심 아키텍처

Adversarial Review는 **Claude와 GPT Codex가 적대적 토론 루프에서 코드를 교차 검증**하는 멀티 에이전트 코드 리뷰 시스템이다. AHOY의 컨센서스 평가와 가장 직접적으로 비교 가능한 프로젝트.

### 4단계 적대적 리뷰 루프

**Phase 1 — Independent Reviews (독립 리뷰)**
- Claude와 Codex가 각각 독립적으로 코드 평가
- 병렬 실행으로 초기 findings 생성

**Phase 2 — Cross-Review (교차 리뷰)**
- Claude가 Codex의 findings를 리뷰 → `claude_on_codex.md`
- Codex가 Claude의 findings를 리뷰 → `codex_on_claude.md`
- 병렬 비판으로 false positive 필터링

**Phase 3 — Meta-Review (메타 리뷰)**
- 각 에이전트가 상대의 비판에 응답
- 결론을 도전하고 입장을 방어
- 구조화된 반론/재반론

**Phase 4 — Synthesis (합성)**
- Claude가 모든 토론 아티팩트를 종합
- 유효한 이슈 확정, 신뢰도 등급 부여
- 수정 사항 구현

### 컨센서스 빌딩

- 양 에이전트가 합의한 이슈 → **높은 신뢰도** 점수
- severity별 이슈 카운트 (critical/high/medium/low)
- 종료 조건 신호로 반복 제어

### 서킷 브레이커

무한 루프 방지 조건:
- 3회 반복에서 0개 수정 적용 → 중단
- 5+ 반복의 지속적 불일치 → 중단
- 3+ 반복에서 동일 unfixable 이슈 반복 → 중단

### 아티팩트 관리

파일 명명 규칙: `iter{N}_{phase}_{agent}_{type}.md`
- 전체 분석, 구조화된 상태 블록, 추론 추적 포함
- 파싱 가능한 필드로 자동화 지원

### 비용 프로파일

최대 3회 반복: 약 21 API 호출 (반복당 7호출 × 2모델 × 4단계)

### 이론적 배경

- D3 (Debate, Deliberate, Decide) 프레임워크
- ChatEval 멀티 에이전트 방법론
- 연구 결론: "멀티 에이전트 토론은 환각과 false positive을 줄인다"

## AHOY 비교 분석

### AHOY보다 나은 점

1. **4단계 적대적 토론 구조**: AHOY는 독립 평가 → 컨센서스 2단계. Adversarial Review는 독립→교차→메타→합성 4단계로 더 깊은 검증. 특히 교차 비판과 메타 리뷰(반론/재반론)가 false positive을 효과적으로 필터링
2. **교차 리뷰 (Cross-Review)**: 평가자 A가 평가자 B의 findings를 직접 비판. AHOY는 평가자들이 서로의 결과를 보지 못하고 독립 평가만 수행
3. **신뢰도 등급 시스템**: 양 에이전트 합의 이슈에 높은 신뢰도 자동 부여. AHOY는 합의 여부만 판단 (pass/fail)
4. **반복 기반 수렴**: 최대 3회 반복으로 토론이 수렴될 때까지 계속. AHOY는 단일 라운드 평가
5. **서킷 브레이커 다중 조건**: 3가지 독립적 중단 조건으로 무한 루프 세밀 방지

### AHOY가 더 나은 점

1. **전체 개발 사이클 커버**: Adversarial Review는 코드 리뷰만. AHOY는 계획→계약→생성→평가 전체 사이클 관리
2. **Hook 기반 하드 차단**: Adversarial Review는 Bash 스크립트로 소프트한 흐름 제어. AHOY는 Hook으로 상태 전이 하드 차단
3. **파일 소유권 분리**: Adversarial Review는 접근 제어 없음
4. **Generator 의견 strip**: 평가 대상(생성 코드)과 평가 결과의 분리 메커니즘 없음
5. **컨텍스트 리셋**: 장기 세션에서 컨텍스트 오염 방지 메커니즘 없음
6. **상태머신**: 명시적 상태 전이 규칙과 rework 제한 없음 (서킷 브레이커만)
7. **성숙도/규모**: 4스타, Bash 단일 스크립트. AHOY보다 프로덕션 준비 수준 낮음

### 배울 만한 구체적 아이디어

1. **교차 리뷰 (Cross-Review) 단계 도입**
   - 현재: Codex와 Gemini가 독립 평가 후 결과를 컨센서스로 합산
   - 개선: Phase 1 독립 평가 → **Phase 2 Codex가 Gemini findings 비판 + Gemini가 Codex findings 비판** → Phase 3 최종 합성
   - 구현: eval_dispatch.py에 cross_review 라운드 추가. Codex findings를 Gemini에게, Gemini findings를 Codex에게 전달하여 비판 요청
   - 효과: false positive 대폭 감소, 평가 품질 향상

2. **신뢰도 등급 (Confidence Rating)**
   - 현재: issues.json에 severity만 존재
   - 개선: `confidence` 필드 추가 (high/medium/low). 양 평가자 합의 = high, 단일 평가자 = medium, 교차 리뷰에서 반박됨 = low
   - 구현: eval_dispatch.py 컨센서스 로직에 신뢰도 산출 추가

3. **반복 평가 수렴 루프**
   - 현재: 단일 라운드 평가 → 결과 확정
   - 개선: 평가자 간 불일치 시 최대 2회 추가 라운드 (교차 비판 → 재평가)
   - 구현: eval_dispatch.py에 `max_eval_rounds=3`, 불일치 감지 시 cross-review 자동 트리거

4. **아티팩트 기반 감사 추적**
   - `iter{N}_{phase}_{evaluator}_{type}.json` 형식으로 평가 과정 전체 기록
   - 구현: `.ahoy/eval_artifacts/` 디렉토리에 라운드별 평가 입출력 자동 저장

## AHOY 개선 제안 Top 3

### 1. 교차 리뷰 (Cross-Review) 평가 단계 도입

> **v0.2.0 구현 완료** — `eval_dispatch.py:build_round2_prompt()` verdict conflict 시 2-Round 교차 검증 자동 실행

- **현재**: Codex와 Gemini가 독립 평가 → 하나라도 fail이면 fail
- **개선**:
  1. Phase 1: Codex와 Gemini 독립 평가 (현재와 동일)
  2. **Phase 2 (신규)**: 불일치 시 교차 리뷰 — Codex findings를 Gemini에게, Gemini findings를 Codex에게 전달하여 각각 "동의/반박" 판정
  3. Phase 3: 교차 리뷰 결과 기반 최종 컨센서스
- **파일**: `eval_dispatch.py` (교차 리뷰 라운드 추가), issues.json 스키마 확장 (`cross_review_status` 필드)
- **효과**: false positive 30-50% 감소, 평가 신뢰도 대폭 향상. 비용은 불일치 시에만 추가 API 호출 발생

### 2. 이슈 신뢰도 등급 시스템 (Confidence Rating)
- **현재**: issues.json에 severity만 존재, 모든 이슈가 동일 가중치
- **개선**: 각 이슈에 `confidence` 필드 추가:
  - `high`: 양 평가자 합의 + 교차 리뷰 확인
  - `medium`: 단일 평가자 발견, 교차 리뷰 미수행
  - `low`: 교차 리뷰에서 반박됨 (하지만 발견자가 재반론)
  - `dismissed`: 교차 리뷰에서 반박되고 발견자도 철회
- **파일**: `eval_dispatch.py` (신뢰도 산출), issues.json 스키마, Hook (confidence=low 이슈는 rework 필수가 아닌 선택)
- **효과**: Generator가 high confidence 이슈에 집중하여 rework 효율 향상

### 3. 다중 조건 서킷 브레이커 강화

> **v0.2.0 구현 완료** — `validate_harness.py:detect_failure_pattern()` 연속 시도 간 반복 이슈 탐지 + `check_circuit_breaker()` post-eval Hook

- **현재**: rework 3회 제한만 존재
- **개선**: 3가지 독립 중단 조건 추가:
  1. **Zero Progress**: rework에서 해결된 이슈 0개 연속 2회 → 자동 중단 + handoff
  2. **Persistent Disagreement**: 평가자 간 동일 이슈 3회 연속 불일치 → 사람 개입 요청
  3. **Identical Unfixable**: 동일 이슈가 3회 연속 "unfixable" 판정 → 해당 이슈 스킵 후 나머지 평가
- **파일**: `eval_dispatch.py` (서킷 브레이커 로직), `.ahoy/circuit_breaker.json` (이력 추적)
- **효과**: 무의미한 rework 반복 조기 탈출, 사람 개입 적시 트리거
