# FareedKhan-dev/agentic-guardrails 분석 리포트

> 분석일: 2026-03-28 (5차)

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | agentic-guardrails |
| URL | https://github.com/FareedKhan-dev/agentic-guardrails |
| 스타 | 35 |
| 라이선스 | 미명시 |
| 핵심 키워드 | 계층적 가드레일, LangGraph, 비동기 병렬 입력 검증, 모델 계층화, ReAct 에이전트 |

## 핵심 아키텍처

### 3계층 방어 체계 (Defense-in-Depth)

```
사용자 입력
    ↓
[Layer 1: Input Guardrails] ← asyncio 병렬 실행
  ├─ 주제 적합성 검사
  ├─ PII/MNPI 탐지
  └─ 컴플라이언스 위반 플래깅
    ↓ (통과 시)
[Layer 2: Action Plan Guardrails] ← 내부 추론 검증
  ├─ AI 정책 강제
  └─ Human-in-the-Loop 에스컬레이션 트리거
    ↓ (통과 시)
[ReAct Agent 실행] (LangGraph StateGraph)
  ├─ query_10K_report (SEC EDGAR 검색)
  ├─ get_real_time_market_data (실시간 시세)
  └─ execute_trade (고위험 매매 실행)
    ↓
[Layer 3: Output Guardrails] ← 최종 검증
  ├─ 정확성 검증
  ├─ 환각 감지
  └─ 인용 검증
    ↓
최종 응답
```

### 모델 계층화 (Model Stratification)

| 역할 | 모델 | 이유 |
|------|------|------|
| 빠른 분류/필터링 | Gemma-2-2B | 낮은 레이턴시, 저비용 |
| 안전 분석 | Llama-Guard-3-8B | 안전 특화 모델 |
| 복잡한 추론 | Llama-3.3-70B | 고품질 판단 |

### LangGraph 기반 ReAct 루프

- `AgentState`에 대화 히스토리를 상태로 관리
- StateGraph로 Reason → Act → Observe 순환 오케스트레이션
- 의도적으로 비보호 에이전트를 먼저 구축하여 실패 모드를 노출시킨 후 가드레일 추가

## AHOY와 비교

### AHOY보다 나은 점

1. **비동기 병렬 입력 가드레일**: AHOY의 PreToolUse Hook은 직렬 실행. agentic-guardrails는 asyncio로 여러 검사를 동시 실행하여 레이턴시 최소화
2. **모델 계층화 (Model Stratification)**: 역할별 최적 모델 배정. AHOY는 Codex/Gemini를 동등하게 사용하지만, 역할별 모델 크기 최적화 없음
3. **Human-in-the-Loop 에스컬레이션**: Layer 2에서 위험도 높은 액션을 사람에게 전달하는 메커니즘 내장. AHOY는 rework 3회 후 수동 개입이지만 명시적 에스컬레이션 경로 없음
4. **의도적 실패 시연**: 비보호 에이전트로 먼저 실패를 보여준 후 가드레일 효과 입증 — 교육/문서화 패턴으로 우수

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리**: agentic-guardrails는 자기평가(같은 파이프라인 내 검증). AHOY는 외부 모델이 평가하여 자기평가 편향 원천 차단
2. **다중 모델 필수 컨센서스**: agentic-guardrails에는 복수 평가자 합의 개념 없음. 단일 모델의 Layer별 판단에 의존
3. **상태머신 기반 스프린트**: agentic-guardrails는 단발성 요청-응답 파이프라인. AHOY의 planned→contracted→generated→passed 사이클과 rework 루프 없음
4. **파일 소유권 분리 및 의견 strip**: 가드레일이 있지만 Generator 출력에서 주관적 판단을 제거하는 메커니즘 없음
5. **계약 기반 개발**: contract.md 같은 Generator-Evaluator 공통 참조점 없음

## 배울 만한 구체적 아이디어

### 1. Hook 병렬 실행 레이어 (즉시 적용 가능)

AHOY의 PreToolUse Hook을 asyncio 기반 병렬 실행으로 전환:

```python
# 현재 AHOY: 직렬 Hook 실행
for hook in pre_tool_hooks:
    result = hook.check(tool_call)
    if result.blocked:
        return block

# 제안: 병렬 Hook 실행
async def run_parallel_hooks(tool_call):
    tasks = [hook.check(tool_call) for hook in pre_tool_hooks]
    results = await asyncio.gather(*tasks)
    return any(r.blocked for r in results)
```

**적용 파일**: `hooks/pre_tool_use.py` — asyncio.gather로 독립적인 검사를 병렬화

### 2. 역할별 모델 계층화

eval_dispatch.py에서 평가 난이도별 모델 배정:

```python
MODEL_TIERS = {
    "syntax_check": "fast-small",      # 빠른 구문 검사
    "logic_review": "codex-standard",   # 로직 검증
    "security_audit": "gemini-pro",     # 보안 심층 분석
}
```

**적용 파일**: `eval_dispatch.py` — 평가 카테고리별 모델 라우팅 로직 추가

### 3. 에스컬레이션 경로 명시화

rework 3회 도달 전 중간 에스컬레이션 트리거 추가:

- rework 1회: 자동 재시도
- rework 2회: `escalation_warning` 플래그 → handoff 문서에 기록
- rework 3회: 강제 중단 + 사람 개입 요청

**적용 파일**: `sprint_state_machine.py` — rework 카운터에 에스컬레이션 레벨 추가

---

## AHOY 개선 제안 Top 3

1. **PreToolUse Hook 비동기 병렬화** — `hooks/pre_tool_use.py`에서 독립적 검사(파일 소유권, 상태 전이, 스코프 검증)를 `asyncio.gather`로 동시 실행. Hook 수 증가 시 레이턴시 선형 증가를 차단하여 확장성 확보

2. **평가 난이도 기반 모델 계층화** — `eval_dispatch.py`에 `MODEL_TIERS` 딕셔너리 추가. 구문/스타일은 경량 모델, 보안/로직은 대형 모델 배정. 평가 비용 30-40% 절감 예상

3. **중간 에스컬레이션 트리거 시스템** — `sprint_state_machine.py`의 rework 카운터에 레벨 개념 추가 (warning → escalate → halt). rework 2회 시점에 handoff 문서 자동 생성하여 사람이 개입할 수 있는 컨텍스트 사전 확보
