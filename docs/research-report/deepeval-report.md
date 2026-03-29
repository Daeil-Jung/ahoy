# DeepEval (confident-ai/deepeval) 분석 리포트

> 분석일: 2026-03-28 (8차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | DeepEval |
| GitHub URL | https://github.com/confident-ai/deepeval |
| 스타 | 14,300+ |
| 최근 커밋 | 2026-03-28 (매우 활발) |
| 라이선스 | Apache 2.0 |
| 언어 | Python |
| 핵심 키워드 | LLM-as-Judge, G-Eval, Agent 평가, Pytest 통합, 다중 메트릭 |

## 핵심 아키텍처

DeepEval은 LLM 애플리케이션을 위한 **Pytest 스타일 단위 테스트 프레임워크**로, LLM-as-Judge 방식과 로컬 NLP 모델을 결합한 다층 평가 시스템을 제공한다.

### 평가 메트릭 체계

**범용 메트릭:**
- **G-Eval**: Chain-of-Thought 기반 LLM-as-Judge, 임의 기준 평가 가능
- **DAG**: 그래프 기반 결정론적 LLM-as-Judge 빌더

**에이전트 전용 메트릭 (AHOY와 가장 관련):**
- **Task Completion**: 에이전트가 목표를 달성했는지 평가
- **Tool Correctness**: 도구 호출 정확성 검증
- **Goal Accuracy**: 최종 결과의 목표 부합도
- **Step Efficiency**: 단계별 효율성 측정
- **Plan Adherence**: 계획 대비 실행 일치도

**RAG 메트릭:**
- Answer Relevancy, Faithfulness, Contextual Recall/Precision, RAGAS

**안전성 메트릭:**
- Hallucination, Bias, Toxicity 감지

**다중 턴 메트릭:**
- Knowledge Retention, Conversation Completeness, Turn Relevancy

### 아키텍처 특징

1. **@observe 데코레이터**: 중첩된 LLM 호출, 리트리버, 도구 상호작용을 자동 추적
2. **컴포넌트 레벨 평가**: v3.0에서 에이전트 전체가 아닌 개별 컴포넌트 단위 평가 지원
3. **프레임워크 통합**: OpenAI, LangChain, LangGraph, Pydantic AI, CrewAI, Anthropic, LlamaIndex
4. **Confident AI 플랫폼**: 데이터셋 관리, 추적, 평가 실행, 프로덕션 모니터링 통합

## AHOY 비교 분석

### AHOY보다 나은 점

1. **세분화된 메트릭 체계**: AHOY의 pass/fail 이진 평가 대비 14+ 독립 메트릭으로 다차원 평가. 특히 Task Completion, Tool Correctness, Plan Adherence는 AHOY contract 평가에 직접 적용 가능
2. **컴포넌트 레벨 분해**: 전체 스프린트가 아닌 개별 도구 호출, 개별 코드 변경 단위로 평가 분해 가능
3. **통계적 평가 신뢰도**: G-Eval의 CoT 기반 평가는 단순 pass/fail보다 일관성 높은 평가 제공
4. **프로덕션 모니터링**: 개발 시점 평가뿐 아니라 배포 후 지속적 품질 모니터링
5. **Pytest 통합**: 기존 CI/CD 파이프라인에 자연스럽게 통합되는 테스트 프레임워크
6. **DAG 기반 결정론적 평가**: 비결정적 LLM 평가를 그래프로 구조화하여 재현 가능성 확보

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리**: DeepEval은 동일 프레임워크 내에서 평가하므로 자기평가 편향 차단 메커니즘 부재
2. **다중 모델 필수 컨센서스**: DeepEval은 단일 모델 평가가 기본. 다중 모델 합의 메커니즘 없음
3. **Hook 기반 하드 차단**: DeepEval은 테스트 실패를 보고하지만 실행을 차단하지 않음. AHOY는 상태 전이 자체를 차단
4. **파일 소유권 분리**: DeepEval은 평가 결과에 대한 쓰기 권한 분리 개념 없음
5. **스프린트 상태머신**: DeepEval은 단순 테스트 실행이며 워크플로우 상태 관리 없음
6. **Generator 의견 strip**: DeepEval은 평가 대상의 주관적 판단 제거 메커니즘 없음

### 배울 만한 구체적 아이디어

1. **G-Eval CoT 프롬프트 패턴**: eval_dispatch.py의 평가 프롬프트에 CoT 강제 삽입 → 평가 품질 향상
   - 구현: eval_dispatch.py에서 평가 프롬프트에 "Step 1: ... Step 2: ..." 구조 강제
2. **DAG 기반 평가 분해**: contract.md 요구사항을 DAG 노드로 분해, 각 노드별 독립 평가
   - 구현: contract.md 파서에 depends_on 필드 추가, eval_dispatch.py에서 DAG 순서 평가
3. **@observe 패턴 차용**: Agent Trace에 데코레이터 기반 자동 추적 적용
   - 구현: Hook에서 도구 호출 자동 로깅을 DeepEval의 @observe 패턴처럼 구조화
4. **Plan Adherence 메트릭**: contract.md 대비 실제 구현의 계획 준수도 정량 측정
   - 구현: eval_dispatch.py에 plan_adherence_score 필드 추가 (0-1 범위)
5. **컴포넌트 레벨 재평가**: rework 시 전체가 아닌 실패 컴포넌트만 재평가
   - 구현: issues.json의 location 기반 부분 재평가 로직

## AHOY 개선 제안 Top 3

### 1. G-Eval CoT 기반 평가 프롬프트 구조화

> **v0.2.0 구현 완료** — `eval_dispatch.py:build_eval_prompt()` 4단계 Chain-of-Thought (Code Understanding → AC Verification → Quality Assessment → Final Verdict)

- **현재**: eval_dispatch.py가 자유 형식으로 평가 요청
- **개선**: 평가 프롬프트에 CoT 단계를 강제 삽입하여 "Step 1: contract 요구사항 나열 → Step 2: 각 요구사항별 구현 확인 → Step 3: 누락/오류 식별 → Step 4: severity 판정"
- **파일**: `eval_dispatch.py`의 평가 프롬프트 템플릿 수정
- **효과**: 평가 일관성 30-50% 향상 기대 (G-Eval 논문 기반)

### 2. Plan Adherence Score (계획 준수도 점수)

> **v0.2.0 구현 완료** — `eval_dispatch.py:_merge_criteria_results()` per-AC convergence_ratio 산출 + harness_state.json 기록

- **현재**: pass/fail 이진 판정만 존재
- **개선**: issues.json에 `plan_adherence_score` (0.0-1.0) 필드 추가. contract.md 요구사항 수 대비 충족 요구사항 비율 자동 산출
- **파일**: `eval_dispatch.py` (점수 산출), `issues.json` (스키마 확장), Hook (점수 기반 전이 규칙)
- **효과**: rework 진행도 정량화, 수렴 여부 조기 감지

### 3. 컴포넌트 레벨 증분 평가 (Incremental Component Evaluation)
- **현재**: rework 시 전체 코드 재평가
- **개선**: issues.json의 location 필드 기반으로 변경된 파일/함수만 재평가. 미변경 부분은 이전 평가 결과 캐시 재사용
- **파일**: `eval_dispatch.py` (diff 기반 평가 범위 결정), `.ahoy/eval_cache/` (평가 캐시 디렉토리)
- **효과**: rework 평가 비용 40-60% 절감, 평가 시간 단축
