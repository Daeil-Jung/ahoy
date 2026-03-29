# metaswarm 분석 리포트

> 분석일: 2026-03-28 (9차)

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | metaswarm |
| GitHub URL | https://github.com/dsifry/metaswarm |
| 스타 | 159 |
| 포크 | 16 |
| 버전 | v0.9.0 (2026-02-27) |
| 커밋 | 834+ |
| 언어 | Shell 57.6%, TypeScript 29.7%, JS 12.7% |
| 라이선스 | MIT |
| 만든이 | Dave Sifry (전 Lyft/Reddit 테크 임원) |

## 핵심 아키텍처

metaswarm는 Claude Code/Gemini CLI/Codex CLI를 위한 **자기 개선 멀티 에이전트 오케스트레이션 프레임워크**로, 프로덕션 SaaS 코드베이스에서 100% 테스트 커버리지로 수백 개의 자율 PR을 생성한 실전 검증된 시스템이다.

### 9단계 워크플로우

```
User Spec / GitHub Issue
        ↓
Swarm Coordinator (worktree 할당, orchestrator 생성)
        ↓
Issue Orchestrator (BEADS epic 생성, 작업 분해)
        ↓
1. Research → 2. Plan → 3. Design Review Gate
        ↓
4. Work Unit Decomposition
        ↓
5. Orchestrated Execution Loop (단위별 4단계)
        ↓
6. Final Review → 7. PR Creation → 8. PR Shepherd → 9. Closure & Learning
```

### 4단계 오케스트레이션 실행 루프 (핵심)

각 작업 단위가 순환:
1. **IMPLEMENT** — 코드 생성 (Codex/Gemini에 위임 가능)
2. **VALIDATE** — 오케스트레이터가 독립적으로 테스트 실행
3. **ADVERSARIAL REVIEW** — 스펙 준수 검증 (file:line 증거 필수)
4. **COMMIT** — 원자적 상태 영속화

> **신뢰 모델**: "오케스트레이터는 독립적으로 검증한다 — 서브에이전트의 자기보고를 절대 신뢰하지 않는다"

### 5인 병렬 설계 리뷰 게이트

5명의 전문가 에이전트가 동시 리뷰:
- Product Manager
- Architect
- Designer
- Security Reviewer
- CTO

최대 3회 반복 후 사람에게 에스컬레이션.

### 18 전문 에이전트 페르소나

Researcher, Architect, Coder, Security Auditor, PR Shepherd, Product Manager, Designer, CTO 등 18개 역할별 에이전트.

### 크로스 모델 리뷰

- 코드를 작성한 모델과 다른 모델이 리뷰
- Claude가 작성 → Codex/Gemini가 리뷰 (또는 역방향)
- 단일 모델 맹점 제거

### TDD 강제 + 커버리지 게이트

`.coverage-thresholds.json`으로 테스트 커버리지 임계값 설정:
- 커버리지 미달 시 PR 생성 차단
- TDD는 선택이 아닌 필수

### PR Shepherd (자율 CI 모니터)

- CI 실패 자동 감지 + 수정
- 리뷰 코멘트 파싱 + 처리
- 스레드 해결 워크플로우
- 자동 머지 조율

### BEADS 지식 관리 시스템

Git-native 태스크 추적:
- 이슈/에픽 관리
- 의존성 그래프
- 지식 베이스 프라이밍

**선택적 프라이밍**: `bd prime --files "path/**" --keywords "term"` — 관련 지식만 로드, 수백 항목에서도 컨텍스트 비대화 방지

### 자기 학습 메커니즘

- `/self-reflect` 명령으로 리뷰어 코멘트에서 패턴 자동 추출
- 빌드/테스트 실패 근본 원인 기록
- 아키텍처 결정 근거 보존
- 사용자 반복/불동의 감지 → 워크플로우 자동 코드화

## AHOY와 비교

### AHOY보다 나은 점

1. **9단계 전체 SDLC 커버리지**: AHOY는 planned→contracted→generated→passed 4단계에 집중. metaswarm는 리서치→설계 리뷰→작업 분해→실행→최종 리뷰→PR 생성→PR 모니터링→학습까지 9단계로 소프트웨어 개발 전체 라이프사이클 관리

2. **5인 병렬 설계 리뷰 게이트**: AHOY는 contracted 단계에서 평가 없음. metaswarm는 5명의 전문가(PM, Architect, Designer, Security, CTO)가 구현 전에 설계를 병렬 검증 — 잘못된 설계가 코드로 변환되기 전 차단

3. **PR Shepherd 자율 CI 루프**: AHOY는 passed 이후 프로세스가 없음. metaswarm는 PR 생성 → CI 모니터링 → 실패 자동 수정 → 머지까지 자율 관리

4. **자기 학습 지식 베이스**: AHOY의 handoff는 세션 간 컨텍스트 전달 목적. metaswarm는 리뷰어 코멘트/실패 패턴/결정 근거를 JSONL로 누적하고 다음 태스크에 선택적 프라이밍

5. **TDD 강제 커버리지 게이트**: AHOY의 평가자는 코드 품질을 LLM으로 판단. metaswarm는 실제 테스트 실행 결과 + 커버리지 수치로 기계적 차단

6. **서브에이전트 자기보고 불신 원칙**: 명시적 "never trusts subagent self-reports" 정책. AHOY도 Generator 의견을 strip하지만, metaswarm는 이를 전체 시스템 원칙으로 격상

### AHOY가 더 나은 점

1. **Generator-Evaluator 물리적 분리**: metaswarm의 adversarial review는 같은 Claude Code 세션 내에서 실행되는 서브에이전트. AHOY는 eval_dispatch.py라는 완전히 다른 프로세스가 외부 API(Codex/Gemini)를 호출하여 구조적 분리 달성

2. **다중 모델 필수 컨센서스**: metaswarm의 크로스 모델 리뷰는 선택적(optionally). AHOY는 최소 2개 외부 모델의 합의가 필수이며 하나라도 fail → 최종 fail

3. **파일 소유권 분리**: metaswarm에는 "이 파일은 이 프로세스만 쓰기 가능" 개념 없음. AHOY의 issues.json 쓰기 권한 분리는 유일무이

4. **Generator 의견 strip**: metaswarm는 서브에이전트 자기보고를 불신하지만, AHOY처럼 보고서에서 주관적 판단을 기계적으로 제거하지는 않음

5. **Hook 기반 하드 차단**: metaswarm의 quality gate는 워크플로우 스크립트 수준. AHOY는 PreToolUse/PostToolUse Hook으로 에이전트 런타임에서 직접 강제

## 배울 만한 구체적 아이디어

### 1. 설계 리뷰 게이트 (contracted 전 검증)

**적용 대상**: planned → contracted 전이에 설계 검증 삽입

```python
# contract.md 검증 에이전트 (eval_dispatch.py 확장)
async def design_review_gate(contract: str) -> ReviewResult:
    reviews = await asyncio.gather(
        evaluate_completeness(contract),     # 요구사항 완전성
        evaluate_feasibility(contract),       # 구현 가능성
        evaluate_scope(contract),             # 범위 적절성
    )
    if any(r.verdict == "REJECT" for r in reviews):
        return ReviewResult(pass_=False, feedback=merge_feedback(reviews))
    return ReviewResult(pass_=True)
```

### 2. 실제 테스트 실행 기반 평가 보강

**적용 대상**: generated → passed 전이에 실행 검증 추가

```python
# eval_dispatch.py에 실행 검증 단계 추가
def run_tests_verification(generated_code_path: str) -> TestResult:
    result = subprocess.run(
        ["pytest", "--cov", "--cov-report=json"],
        cwd=generated_code_path, capture_output=True
    )
    coverage = parse_coverage(result)
    if coverage < THRESHOLD:
        return TestResult(passed=False, reason=f"Coverage {coverage}% < {THRESHOLD}%")
    return TestResult(passed=True, coverage=coverage)
```

### 3. 선택적 지식 프라이밍 (handoff 최적화)

**적용 대상**: handoff 문서 생성 시

```python
# handoff 문서에 관련 지식만 선택적 포함
def prime_handoff(contract: str, knowledge_base: list[dict]) -> str:
    keywords = extract_keywords(contract)
    relevant = [
        entry for entry in knowledge_base
        if any(kw in entry["content"] for kw in keywords)
    ]
    return format_handoff(relevant[:10])  # 상위 10개만
```

### 4. 자기 학습 패턴 수집기

**적용 대상**: 신규 `sprint_learning.py`

```python
# passed/failed 스프린트에서 패턴 자동 추출
def extract_learning(sprint_result: SprintResult) -> Learning:
    if sprint_result.rework_count > 0:
        return Learning(
            type="failure_pattern",
            pattern=sprint_result.common_issue_categories,
            fix=sprint_result.successful_rework_strategy,
        )
    return Learning(type="success_pattern", ...)
```

### 5. PR Shepherd 패턴 (passed 이후 자동화)

**적용 대상**: passed 상태 이후 확장

AHOY는 passed에서 끝나지만, PR 생성→CI 실행→실패 수정→머지까지 자동화 가능:
- passed → pr_created → ci_running → ci_passed → merged
- CI 실패 시 자동 rework 재진입

---

## AHOY 개선 제안 Top 3

### 1. 설계 리뷰 게이트 (planned → contracted 전이 강화)

**구현 방향**: contracted 진입 전 contract.md를 3가지 관점(완전성/구현가능성/범위적절성)에서 자동 검증. 검증 실패 시 피드백과 함께 contract 수정 요구. 최대 3회 반복.

**변경 파일**:
- `eval_dispatch.py` — `design_review()` 함수 추가
- `hooks/pre_tool_use.py` — contracted 전이 시 설계 리뷰 결과 확인
- 신규 `design_review_rubric.yaml` — 리뷰 기준 외부화

### 2. 실행 기반 검증 레이어 (generated → passed 보강)

**구현 방향**: LLM 평가 외에 실제 테스트 실행(pytest/npm test) 결과를 passed 판정 조건에 추가. 커버리지 임계값을 `.ahoy/coverage_thresholds.json`으로 관리.

**변경 파일**:
- `eval_dispatch.py` — 테스트 실행 + 커버리지 검증 추가
- 신규 `.ahoy/coverage_thresholds.json` — 커버리지 임계값
- `hooks/post_tool_use.py` — 테스트 결과 기반 상태 전이 조건 추가

### 3. 스프린트 학습 누적 시스템 (JSONL 지식 베이스)

**구현 방향**: 매 스프린트 종료 시 (passed든 rework 실패든) 패턴을 `.ahoy/knowledge_base.jsonl`에 누적. 다음 스프린트의 contract.md 생성 시 관련 패턴만 선택적으로 주입. handoff에도 관련 지식 자동 포함.

**변경 파일**:
- 신규 `sprint_learning.py` — 패턴 추출 + JSONL 기록
- `eval_dispatch.py` — 평가 결과에서 학습 데이터 추출
- handoff 생성 로직 — 관련 지식 선택적 포함
- 신규 `.ahoy/knowledge_base.jsonl` — 누적 학습 데이터
