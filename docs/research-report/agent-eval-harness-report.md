# Agent Eval Harness 분석 리포트

> 분석일: 2026-03-28 (9차)

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | @plaited/agent-eval-harness |
| GitHub URL | https://github.com/plaited/agent-eval-harness |
| 스타 | 2 |
| 커밋 | 69 (main) |
| 언어 | TypeScript (Bun 최적화) |
| 라이선스 | ISC |
| 패키지 | npm (@plaited/agent-eval-harness) |

## 핵심 아키텍처

Agent Eval Harness는 AI 코딩 에이전트의 실행 궤적을 캡처하고, pass@k/pass^k 메트릭으로 평가하며, 멀티런 비교를 수행하는 **Unix 파이프라인 스타일 CLI 도구**다.

### Unix 파이프라인 설계 철학

두 가지 커맨드 패밀리:

**통합 커맨드** (단일 호출로 전체 워크플로우):
- `capture` — 프롬프트 실행 + 궤적 기록
- `trials` — 멀티런 평가 (pass@k, pass^k)
- `summarize` — 궤적 요약 생성
- `calibrate` — 실패 샘플링 (그레이더 검증)
- `validate-refs` — 참조 솔루션 검증
- `balance` — 테스트 셋 분포 분석
- `schemas` — Zod → JSON Schema 내보내기

**파이프라인 커맨드** (조합 가능):
- `run` → `extract` → `grade` → `format` → `compare`
- 각 단계를 독립적으로 조합, JSONL 스트리밍

### 스키마 기반 어댑터

**헤드리스 어댑터**: JSON 스키마로 CLI 에이전트 상호작용 패턴 기술
- Claude, Gemini 사전 빌트 스키마 제공
- 커스텀 에이전트용 스키마 작성 가이드
- JSON 출력 지원하는 모든 CLI 에이전트 호환
- 제로 설정 어댑터 생성

### 궤적 캡처 (CaptureResult)

```json
{
  "id": "task-1",
  "input": "Fix the login bug",
  "trace": [/* thoughts, messages, tool_calls, plans */],
  "toolErrors": false,
  "exitInfo": {"exitCode": 0, "signal": null, "timedOut": false},
  "timing": {"durationMs": 45230},
  "score": {"value": 0.95, "reasoning": "All tests pass"},
  "metadata": {"trajectoryRichness": "full"}
}
```

- JSONL 형식 스트리밍 출력
- `trajectoryRichness` 분류: "full" / "messages-only" / "minimal"

### 그레이딩 방식

**Git 기반 결과 그레이딩**:
- 실제 환경 변화 감지 (파일 생성, 테스트 결과, 빌드 성공)
- git status + subprocess 실행으로 결과 검증
- 명령 인젝션 방어

**출력 기반 그레이딩**:
- 에이전트 응답 직접 분석
- TypeScript/JavaScript + Python 스크립트 지원
- stdin/stdout JSON 프로토콜

### 평가 메트릭

- **pass@k**: k회 독립 시행 중 성공률
- **pass^k**: 신뢰성 분석용 보완 메트릭
- 구조화된 그레이더 스코어링 (float + reasoning)
- 가중/통계 비교 전략

### 멀티런 비교

`compare` 커맨드로:
- 결과 형식 자동 감지
- 가중 집계 전략
- 통계 분석
- 커스텀 비교 로직

## AHOY와 비교

### AHOY보다 나은 점

1. **pass@k/pass^k 메트릭 시스템**: AHOY는 단일 평가의 pass/fail만 기록. Agent Eval Harness는 동일 태스크를 k번 독립 실행하여 통계적 신뢰도 산출. 평가의 재현성과 신뢰도를 정량화

2. **궤적(Trajectory) 캡처**: AHOY는 평가 결과(issues.json)만 기록. Agent Eval Harness는 에이전트의 사고/메시지/도구호출/계획 전체를 JSONL로 캡처. 실패 원인 사후 분석에 필수

3. **Unix 파이프라인 조합성**: AHOY의 eval_dispatch.py는 모놀리식. Agent Eval Harness는 run→extract→grade→format→compare 각 단계를 독립적으로 조합. 평가 파이프라인 커스터마이징 자유도 극대화

4. **스키마 기반 어댑터**: AHOY는 Codex/Gemini를 eval_dispatch.py에 하드코딩. Agent Eval Harness는 JSON 스키마만 작성하면 어떤 CLI 에이전트든 평가 가능

5. **Git 기반 결과 그레이딩**: LLM 판단이 아닌 실제 git status/테스트 실행으로 결과 검증. 결정론적 평가

6. **멀티런 통계 비교**: 여러 실행의 성능을 통계적으로 비교하여 평가 노이즈 필터링

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리**: Agent Eval Harness는 단일 에이전트 평가 도구. 코드 생성과 평가의 분리 개념 없음

2. **다중 모델 필수 컨센서스**: Agent Eval Harness는 단일 그레이더 실행. AHOY의 다중 평가자 합의 체계 없음

3. **스프린트 상태머신**: Agent Eval Harness는 정적 벤치마크 도구. 개발 사이클(rework 루프, 상태 전이) 없음

4. **Hook 기반 하드 차단**: 런타임 에이전트 행동 제어 메커니즘 없음. 사후 평가만 수행

5. **파일 소유권 분리 / Generator 의견 strip**: 평가 파이프라인 도구이므로 이러한 에이전트 거버넌스 기능 불해당

## 배울 만한 구체적 아이디어

### 1. pass@k 메트릭 도입 (평가 신뢰도 정량화)

**적용 대상**: `eval_dispatch.py` 평가 결과에 신뢰도 산출

```python
import math

def pass_at_k(n: int, c: int, k: int) -> float:
    """n: 총 시행 횟수, c: 성공 횟수, k: 샘플 크기"""
    if n - c < k:
        return 1.0
    return 1.0 - math.prod((n - c - i) / (n - i) for i in range(k))

# 동일 코드를 3번 독립 평가
results = [evaluate(code, contract) for _ in range(3)]
successes = sum(1 for r in results if r.passed)
confidence = pass_at_k(n=3, c=successes, k=1)
# confidence가 낮으면 추가 평가 요청
```

### 2. 궤적 캡처 (Agent Trace 강화)

**적용 대상**: Generator 실행 궤적 JSONL 기록

```python
@dataclass
class TraceEntry:
    timestamp: str
    agent: str  # "generator" | "evaluator_codex" | "evaluator_gemini"
    action_type: str  # "tool_call" | "thought" | "message"
    content: dict
    duration_ms: int

def capture_trace(sprint_id: str, entries: list[TraceEntry]):
    path = f".ahoy/traces/{sprint_id}.jsonl"
    with open(path, "a") as f:
        for entry in entries:
            f.write(json.dumps(asdict(entry)) + "\n")
```

### 3. Git 기반 결정론적 그레이딩

**적용 대상**: generated → passed 전이에 결정론적 검증 추가

```python
def git_based_grading(workspace: str, expected_files: list[str]) -> GradeResult:
    # 1. 예상 파일 존재 확인
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, cwd=workspace)
    created_files = parse_git_status(status.stdout)

    # 2. 테스트 실행
    test_result = subprocess.run(["pytest", "--tb=short"], capture_output=True, cwd=workspace)

    # 3. 결정론적 점수 산출
    file_score = len(set(expected_files) & set(created_files)) / len(expected_files)
    test_passed = test_result.returncode == 0

    return GradeResult(
        file_coverage=file_score,
        tests_passed=test_passed,
        deterministic_score=file_score * 0.4 + (1.0 if test_passed else 0.0) * 0.6
    )
```

### 4. 평가 파이프라인 조합 패턴

**적용 대상**: `eval_dispatch.py` 리팩토링

모놀리식 eval_dispatch.py를 파이프라인 단계로 분리:
```python
# 각 단계가 독립 실행 가능
pipeline = (
    ExtractStep(code_path, contract_path)    # 코드+계약 추출
    | PreScanStep()                           # 정적 사전 검사
    | EvalStep(evaluators=["codex", "gemini"]) # LLM 평가
    | TestRunStep()                            # 실제 테스트 실행
    | ConsensusStep(threshold=1.0)             # 컨센서스 도출
    | FormatStep(output="issues.json")         # 결과 포맷팅
)
result = await pipeline.execute()
```

---

## AHOY 개선 제안 Top 3

### 1. pass@k 평가 신뢰도 시스템

**구현 방향**: 평가 신뢰도가 중요한 경우(보안 이슈, critical severity) 동일 코드를 k=3회 독립 평가. pass@k 점수가 임계값 미만이면 추가 평가자 투입 또는 사람 에스컬레이션. 일반 이슈는 k=1 유지하여 비용 절감.

**변경 파일**:
- `eval_dispatch.py` — pass@k 계산 로직 + 조건부 반복 평가
- 신규 `.ahoy/eval_confidence.json` — severity별 k값 설정
- `issues.json` 스키마 — `confidence_score` 필드 추가

### 2. Generator 궤적 캡처 시스템

**구현 방향**: Generator 세션의 모든 도구 호출을 `.ahoy/traces/{sprint_id}.jsonl`에 캡처. handoff 문서에 궤적 요약 자동 포함. rework 시 이전 궤적을 참조하여 동일 실수 방지.

**변경 파일**:
- `hooks/post_tool_use.py` — 도구 호출마다 궤적 기록
- 신규 `trace_capture.py` — JSONL 기록 + 요약 생성
- handoff 생성 로직 — 궤적 요약 포함

### 3. 평가 파이프라인 조합 패턴 (eval_dispatch 리팩토링)

**구현 방향**: eval_dispatch.py를 ExtractStep→PreScanStep→EvalStep→TestRunStep→ConsensusStep→FormatStep 파이프라인으로 리팩토링. 각 단계를 독립 테스트/교체 가능. 프로젝트별로 다른 파이프라인 구성 가능.

**변경 파일**:
- `eval_dispatch.py` — 파이프라인 아키텍처 리팩토링
- 신규 `eval_pipeline/` 디렉토리 — 각 단계별 모듈
- 신규 `.ahoy/eval_pipeline.json` — 파이프라인 구성 설정
