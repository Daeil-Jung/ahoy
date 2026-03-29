# Strands Agents Evals 분석 리포트

> 분석일: 2026-03-28 (4차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Strands Agents Evals |
| GitHub URL | https://github.com/strands-agents/evals |
| 스타 | 93 |
| 최근 커밋 | 2026-03 (활발한 개발 중, 35 이슈 / 14 PR 오픈) |
| 라이선스 | Apache-2.0 (추정) |
| 언어 | Python 3.10+ |
| PyPI | strands-agents-evals |

## 핵심 아키텍처

### 구조 개요

Strands Evals는 **AWS가 지원하는** AI 에이전트 평가 프레임워크로, 단순 출력 검증부터 복잡한 다중 에이전트 상호작용 분석까지 포괄한다.

```
Cases (테스트 시나리오)
  → Experiments (실험 오케스트레이션)
    → Evaluators (평가 엔진)
      → EvaluationOutput (구조화된 결과)
```

### 핵심 모듈

| 모듈 | 역할 |
|------|------|
| `strands_evals.evaluators` | 빌트인 평가자 클래스 (LLM-as-Judge 포함) |
| `strands_evals.extractors` | 궤적/도구 사용 데이터 추출 (tools_use_extractor 등) |
| `strands_evals.telemetry` | OpenTelemetry 기반 스팬 수집/세션 매핑 |
| `strands_evals.mappers` | StrandsInMemorySessionMapper |
| `strands_evals.generators` | 자동화된 실험 생성 |
| `strands_evals.simulators` | ActorSimulator (동적 대화 생성) |

### 5종 평가 유형

1. **Output Evaluation** — 커스텀 루브릭 기반 LLM 평가
2. **Trajectory Analysis** — 도구 사용 순서 및 액션 시퀀스 평가
3. **Trace-Based Assessment** — OpenTelemetry 스팬 기반 행동 분석
4. **Interaction Evaluation** — 다중 에이전트 핸드오프/협력 평가
5. **Tool Evaluation** — 도구 선택 정확도 및 파라미터 정확성

### LLM-as-Judge 구현

- 유연한 커스텀 루브릭으로 채점 기준 정의
- 구성 가능한 Judge 모델 (Claude 변형 지원)
- 컨텍스트 포함 옵션으로 풍부한 평가
- 추론 과정 + 점수가 포함된 구조화된 출력

### ActorSimulator

- 목표 지향적 다중 턴 대화 동적 생성
- 에이전트 행동 기반 적응형 응답
- 사전 정의된 대화 스크립트 불필요
- Trace 기반 평가자와 통합

## AHOY와의 비교

### AHOY보다 나은 점

| 영역 | Strands Evals | AHOY |
|------|---------------|------|
| **평가 유형 다양성** | 5종 (출력/궤적/트레이스/상호작용/도구) | 코드 품질 중심 단일 평가 |
| **LLM-as-Judge 추상화** | 루브릭 기반 플러거블 평가자 | eval_dispatch.py 하드코딩 |
| **관측성** | OpenTelemetry 네이티브 통합 | 로그 기반 |
| **실험 자동화** | Cases→Experiments→Evaluators 파이프라인 | 수동 스프린트 관리 |
| **시뮬레이터** | ActorSimulator로 엣지케이스 자동 생성 | 없음 |
| **확장성** | 커스텀 Evaluator 클래스 상속으로 확장 | 평가자 추가 시 코드 수정 필요 |

### AHOY가 더 나은 점

| 영역 | AHOY | Strands Evals |
|------|------|---------------|
| **Generator-Evaluator 분리** | 구조적으로 다른 모델 사용 강제 | 같은 모델로 평가 가능 (자기평가 편향 위험) |
| **컨센서스 메커니즘** | 다중 모델 필수 합의 + 하나라도 fail→전체 fail | 단일 평가자 또는 가중 평균 |
| **하드 차단** | Hook으로 상태 전이 강제 | 소프트 평가만 (차단 없음) |
| **파일 소유권 분리** | issues.json 쓰기 권한 격리 | 파일 보안 메커니즘 없음 |
| **주관적 판단 제거** | gen_report에서 의견 strip | 평가자 편향 관리 없음 |
| **스프린트 상태머신** | planned→contracted→generated→passed | 실험 라이프사이클만 (워크플로우 강제 없음) |

## 배울 만한 구체적 아이디어

### 1. Trajectory Evaluator 패턴
```python
# AHOY에 적용: eval_dispatch.py에 궤적 평가 추가
class TrajectoryEvaluator:
    def evaluate(self, tool_calls: list, expected_sequence: list) -> EvalResult:
        """Generator의 도구 호출 순서가 contract.md 기대 순서와 일치하는지 평가"""
        pass
```
- **적용 대상**: `eval_dispatch.py`
- **효과**: Generator가 올바른 순서로 작업했는지 검증 (예: 테스트 작성 → 구현 → 리팩토링)

### 2. 루브릭 기반 평가 템플릿
```yaml
# eval_rubrics/code_quality.yaml
criteria:
  - name: "contract_compliance"
    weight: 0.4
    scoring: "1-5 scale, contract.md 요구사항 충족도"
  - name: "code_correctness"
    weight: 0.3
  - name: "security"
    weight: 0.2
  - name: "maintainability"
    weight: 0.1
```
- **적용 대상**: `eval_dispatch.py` 프롬프트 시스템
- **효과**: 평가 기준을 코드에서 분리하여 비개발자도 조정 가능

### 3. OpenTelemetry 기반 Agent Trace
- AHOY의 제안된 "Agent Trace 시스템"을 OpenTelemetry 표준으로 구현
- 스팬으로 각 도구 호출의 시작/종료/결과를 기록
- handoff 문서 자동 생성에 활용

---

## AHOY 개선 제안 Top 3

### 1. 루브릭 기반 평가 외부화 시스템
- **현재**: eval_dispatch.py에 평가 기준이 프롬프트로 하드코딩
- **개선**: `eval_rubrics/` 디렉토리에 YAML 루브릭 파일로 분리
- **구현 방향**:
  - `eval_rubrics/default.yaml` — 기본 평가 루브릭
  - `eval_dispatch.py`에서 루브릭 로드 → 프롬프트 동적 생성
  - contract.md에 `eval_rubric: security_focused` 같은 필드 추가
  - 도메인별 루브릭 (보안 중심, 성능 중심, API 호환성 중심) 전환 가능

### 2. 궤적 평가 (Trajectory Evaluation) 도입
- **현재**: 최종 코드만 평가, 생성 과정은 무시
- **개선**: Generator의 도구 호출 시퀀스를 평가 대상에 포함
- **구현 방향**:
  - PostToolUse Hook에서 도구 호출 로그를 `sprint_trace.jsonl`에 기록
  - eval_dispatch.py에 trajectory 검증 단계 추가
  - 예: "테스트 없이 구현 완료 선언" → 자동 fail
  - contract.md에 `expected_trajectory` 섹션 추가

### 3. ActorSimulator 기반 계약 검증
- **현재**: contract.md는 정적 문서, 모호성 사전 검증 없음
- **개선**: contracted 상태 진입 시 시뮬레이터로 계약 완전성 검증
- **구현 방향**:
  - `contract_validator.py` 신규 모듈
  - LLM에게 "이 contract로 구현할 때 모호한 부분" 질문
  - 발견된 모호성을 Generator에게 사전 경고
  - planned→contracted 전이 시 자동 실행
