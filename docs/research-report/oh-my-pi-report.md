# oh-my-pi (can1357) 분석 리포트

> 분석일: 2026-03-29

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | oh-my-pi |
| URL | https://github.com/can1357/oh-my-pi |
| 스타 | 2,400+ |
| 최근 활동 | v13.16.0 (2026-03-27), 활발한 릴리스 |
| 라이선스 | MIT |
| 핵심 키워드 | Hash-Anchored Edits, LSP 통합, 6 서브에이전트, Reviewer, AST, Bun 런타임 |

## 핵심 아키텍처

### 설계 철학

"최소 도구, 최대 표현력" — 기본 4개 도구(read, write, edit, bash)만 제공하고, TypeScript 확장/스킬/프롬프트 템플릿/테마로 커스터마이징. 플러그인이 아닌 **피 패키지(Pi Package)**로 npm/git 배포.

### Hash-Anchored Edits (Hashline)

모든 줄에 짧은 콘텐츠 해시 앵커를 부여. 모델이 텍스트 재현 대신 앵커를 참조하여 편집.

**장점**:
- 공백 재현 오류 제거
- "string not found" 에러 제거
- 모호한 매칭 제거
- 파일 변경 시 해시 불일치 → 편집 자동 거부 (corruption 방지)
- 출력 토큰 61% 절감 (Grok 4 Fast 기준)

**벤치마크**: 16개 모델, 180 태스크, 3회 반복 측정
- Grok Code Fast 1: 6.7% → 68.3% 성공률 향상
- Gemini 3 Flash: str_replace 대비 +5pp

### LSP 통합

11개 LSP 작업 네이티브 지원: diagnostics, definition, type_definition, implementation, references, hover, symbols, rename, code_actions, status, reload

### 6 서브에이전트

| 에이전트 | 역할 |
|----------|------|
| explore | 대규모 코드베이스 탐색 |
| plan | 구현 계획 수립 |
| designer | UI/UX 설계 |
| reviewer | 구조화된 코드 리뷰 (P0-P3 우선순위) |
| task | 일반 태스크 실행 |
| quick_task | 빠른 소규모 태스크 |

### Reviewer 에이전트

- 3가지 리뷰 모드: 브랜치 비교, 미커밋 변경, 커밋 리뷰
- `report_finding` 도구로 구조화된 발견 보고 (P0: critical → P3: nit)
- 자동 verdict 렌더링: approve / request-changes / comment
- explore 에이전트 병렬 스폰으로 대규모 코드베이스 분석 지원

### Hook 시스템

TypeScript 모듈 기반 라이프사이클 Hook. 동적 모듈 임포트로 로드, 실패 시 `LoadHooksResult.errors`에 보고.

### 4가지 실행 모드

1. Interactive: 대화형 터미널
2. Print/JSON: 비대화형 출력
3. RPC: 프로세스 통합
4. SDK: 앱 내장

## AHOY와 비교

### AHOY보다 나은 점

1. **Hash-Anchored Edits**: 편집 정확성과 토큰 효율을 동시에 해결하는 혁신적 접근. 출력 토큰 61% 절감은 평가 비용에도 직접 영향. AHOY에는 편집 도구 최적화 개념 없음.
2. **LSP 네이티브 통합**: 11개 LSP 작업으로 정적 분석 품질 극대화. AHOY는 lint/type-check를 CLI 명령으로 실행하지만 LSP 수준 실시간 진단은 없음.
3. **구조화된 리뷰 우선순위 (P0-P3)**: reviewer 에이전트의 4단계 우선순위 분류. AHOY의 issues.json은 severity 필드가 있지만 표준화된 P0-P3 체계는 아님.
4. **벤치마크 기반 검증**: 16모델×180태스크×3회 반복 체계적 벤치마크. AHOY는 하네스 자체의 성능 벤치마크가 없음.
5. **SDK/RPC 모드**: 외부 시스템 통합 용이. AHOY는 CLI 플러그인 전용.

### AHOY가 더 나은 점

1. **Generator-Evaluator 물리적 분리**: oh-my-pi의 reviewer는 동일 프레임워크 내 서브에이전트. AHOY는 eval_dispatch.py가 완전 별도 프로세스 + 외부 모델 → 자기평가 편향 불가.
2. **다중 모델 컨센서스**: oh-my-pi의 reviewer는 단일 모델(동일 LLM). AHOY는 최소 2개 외부 모델 합의 필수.
3. **any fail → final fail**: oh-my-pi는 approve/request-changes/comment 3단계. AHOY는 하나라도 fail이면 전체 fail.
4. **상태머신 강제**: oh-my-pi는 자유로운 명령 기반 진행. AHOY는 상태 전이를 Hook으로 하드 차단.
5. **파일 소유권 차단**: oh-my-pi의 Hash-Anchored Edits는 "파일 변경 감지"이지 "파일 접근 권한 분리"가 아님. AHOY는 issues.json 쓰기 자체를 셸 수준 차단.
6. **Generator 의견 제거**: oh-my-pi에는 평가 입력에서 생성자 주관을 제거하는 메커니즘 없음.

## 배울 만한 구체적 아이디어

### 1. Hash-Anchored Edit 검증 패턴

Hashline의 "파일 변경 시 해시 불일치 → 편집 거부" 패턴을 AHOY의 **PostToolUse Edit Hook**에 적용 가능:

**적용 방향**: Edit Hook에서 편집 전 파일 해시 ↔ 마지막 Read 시점 해시 비교. 불일치 시 "stale read" 경고 또는 차단. concurrent modification 방지.

### 2. P0-P3 우선순위 체계

issues.json의 이슈에 표준화된 우선순위 등급 적용:

**적용 방향**: `eval_dispatch.py`의 JSON 스키마에 `priority: P0|P1|P2|P3` 필드 추가. P0(critical)이 하나라도 있으면 무조건 fail, P2-P3만 있으면 경고만 발행하는 **차등 대응** 가능성 검토. (단, "any fail → final fail" 원칙과의 조화 필요.)

### 3. 벤치마크 프레임워크 도입

oh-my-pi의 16모델×180태스크×3회 반복 벤치마크 방법론을 참고하여 AHOY 하네스 자체의 성능 측정 체계 구축:

**적용 방향**: `benchmarks/` 디렉토리에 표준 태스크 세트 + 자동 실행 스크립트. 하네스 변경 시 회귀 테스트로 활용.

---

## AHOY 개선 제안 Top 3

### 1. Stale-Read 감지 Hook (Hash-Anchored 영감)

**현재**: PostToolUse Edit Hook이 `echo` 기반 안내만 수행 (GAP-2).
**제안**: Edit 호출 시 대상 파일의 마지막 Read 시점 해시와 현재 파일 해시 비교. 불일치 시 "stale read — re-read required" 경고 + 선택적 차단. Generator가 오래된 파일 상태 기반으로 편집하는 것을 방지.
**변경 대상**: `validate_harness.py` (PostToolUse Edit에 해시 비교 로직 추가), `hooks/hooks.json` (PostToolUse Edit 핸들러 교체)

### 2. 이슈 우선순위 스키마 표준화

**현재**: issues.json에 severity 필드는 있으나 비표준.
**제안**: P0(blocker)/P1(critical)/P2(major)/P3(minor) 4단계 표준 도입. 평가 프롬프트에 "각 이슈에 P0-P3 우선순위 부여 필수" 지시. rework 시 P0/P1 이슈만 우선 해결하도록 피드백 구조화.
**변경 대상**: `eval_dispatch.py` (JSON 스키마 + 프롬프트), `skills/ahoy-gen/SKILL.md` (rework 시 우선순위 기반 처리)

### 3. 하네스 벤치마크 태스크 세트

**현재**: AHOY 하네스 자체의 성능을 객관적으로 측정하는 방법 없음.
**제안**: `benchmarks/` 디렉토리에 5-10개 표준 코딩 태스크 (다양한 난이도/언어) + 기대 결과 정의. 하네스 변경 시 자동 실행하여 pass율/rework 횟수/토큰 사용량 회귀 측정.
**변경 대상**: 신규 `benchmarks/` 디렉토리, CI 스크립트
