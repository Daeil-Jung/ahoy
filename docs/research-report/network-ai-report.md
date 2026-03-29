# Network-AI 분석 리포트

> 분석일: 2026-03-28 (9차)

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Network-AI |
| GitHub URL | https://github.com/jovanSAPFIONEER/Network-AI |
| 스타 | 29 |
| 커밋 | 256 (main) |
| 버전 | v4.11.2 |
| 언어 | TypeScript 5.x (Node.js ≥18) |
| 라이선스 | MIT |
| 테스트 | 1,684 passing |

## 핵심 아키텍처

Network-AI는 TypeScript/Node.js 기반 **멀티 에이전트 오케스트레이션 프레임워크**로, 병렬 에이전트가 공유 상태에 동시 쓰기할 때 발생하는 split-brain 문제를 해결하는 데 집중한다.

### LockedBlackboard (원자적 공유 상태)

3단계 커밋 프로토콜로 동시 쓰기 충돌을 방지:

```typescript
const id = board.propose('key', value, 'agent-id');
board.validate(id, 'agent-id');
board.commit(id);
```

- 파일시스템 수준 mutex로 원자성 보장
- 우선순위 기반 선점 (높은 우선순위 쓰기가 같은 키 선점)
- propose → validate → commit 3단계 실패 시 자동 롤백

### FSM 거버넌스

- 에이전트별 상태 경계 하드스톱 (700ms 타임아웃)
- 전이 규칙 위반 실시간 감지
- 모든 전이를 감사 로그에 기록
- 설정 가능한 타임아웃 강제

### 권한 게이팅 (AuthGuardian)

- HMAC + Ed25519 서명 토큰
- Deny-by-default 정책 모델
- 에이전트별 + 리소스별 스코프 제어 (blackboard, budget 등)
- 토큰 생성/취소 사유 추적

### FederatedBudget (토큰 예산)

- 에이전트별 하드 토큰 상한
- 실시간 비용 추적
- 분산 노드 간 예산 조율

### 컴플라이언스 모니터링

4종 실시간 위반 감지:
- **TOOL_ABUSE**: 미인가 함수 호출
- **TURN_TAKING**: 통신 순서 위반
- **RESPONSE_TIMEOUT**: 응답 마감 초과
- **JOURNEY_TIMEOUT**: 프로젝트 수준 시간 제한

### 17 프레임워크 어댑터

LangChain, AutoGen, CrewAI, MCP, LlamaIndex, SemanticKernel, OpenAI Assistants, Haystack, DSPy, Agno, OpenClaw, A2A, Codex, MiniMax, NemoClaw, APS, Custom — 제로 어댑터 의존성(클라이언트 라이브러리 BYO).

### 감사 로그

- JSONL 형식 append-only 로그
- 모든 쓰기/권한 부여/FSM 전이에 암호화 서명
- 쿼리 + 실시간 tail 기능

### ProjectContextManager (Layer 3)

Python 헬퍼로 매 시스템 프롬프트에 프로젝트 지속 상태 주입:
- 이전 결정사항/목표
- 기술 스택 컨텍스트
- 마일스톤 추적
- 금지 패턴/제약사항

## AHOY와 비교

### AHOY보다 나은 점

1. **LockedBlackboard 원자적 공유 상태**: AHOY의 issues.json은 단순 파일 소유권 분리인 반면, Network-AI는 propose→validate→commit 3단계 프로토콜로 병렬 에이전트 간 데이터 무결성을 보장. 여러 평가자가 동시에 결과를 기록할 때 충돌 방지 가능

2. **17 프레임워크 어댑터**: AHOY는 Codex+Gemini 2개 평가자에 하드코딩. Network-AI는 어댑터 패턴으로 14+ 프레임워크를 플러그인 방식으로 지원. 새 평가 모델 추가 시 어댑터 하나만 구현

3. **토큰 예산 하드 상한**: AHOY에는 비용 관리 메커니즘 없음. Network-AI는 에이전트별 토큰 ceiling을 인프라 수준에서 강제하여 runaway cost 방지

4. **암호화 감사 로그**: AHOY의 Hook은 상태 전이를 강제하지만 감사 추적이 없음. Network-AI는 HMAC 서명 JSONL 로그로 모든 작업을 검증 가능하게 기록

5. **컴플라이언스 위반 분류 체계**: 4종(TOOL_ABUSE, TURN_TAKING, RESPONSE_TIMEOUT, JOURNEY_TIMEOUT) 위반 유형 자동 분류는 AHOY의 단순 pass/fail보다 풍부한 진단 정보 제공

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리**: Network-AI는 에이전트 간 조율 프레임워크일 뿐, 코드 생성과 평가의 구조적 분리가 없음. 자기평가 편향 차단 메커니즘 부재

2. **다중 모델 필수 컨센서스**: Network-AI는 합의 메커니즘 없이 공유 상태 기반 조율. AHOY의 "하나라도 fail → 최종 fail" 엄격 기준 없음

3. **스프린트 상태머신**: Network-AI의 FSM은 에이전트 수준 거버넌스(타임아웃, 권한)에 집중. AHOY의 planned→contracted→generated→passed 개발 워크플로우 상태머신과 성격이 다름

4. **Generator 의견 제거**: Network-AI는 에이전트 출력을 그대로 전달. AHOY의 gen_report에서 주관적 판단 strip은 유일무이

5. **파일 소유권 분리**: Network-AI의 AuthGuardian은 리소스 접근 제어이지만, AHOY처럼 "이 파일은 이 프로세스만 쓰기 가능"이라는 파일 단위 소유권 분리는 아님

## 배울 만한 구체적 아이디어

### 1. 3단계 커밋 프로토콜 (issues.json 원자적 쓰기)

**적용 대상**: `eval_dispatch.py`의 issues.json 쓰기

현재 eval_dispatch.py가 단독 쓰기하므로 충돌은 없지만, 향후 병렬 평가 시:
```python
# propose → validate → commit 패턴
proposal = evaluator.propose_issues(sprint_id, findings)
validated = consensus_engine.validate(proposal)
if validated:
    issues_store.commit(proposal)
```

### 2. 컴플라이언스 위반 분류 체계

**적용 대상**: Hook 위반 로깅

현재 Hook은 단순 차단(block)만 수행. 위반 유형을 분류하여 패턴 분석 가능:
```python
VIOLATION_TYPES = {
    "SCOPE_ESCAPE": "contract 범위 외 파일 수정",
    "STATE_SKIP": "상태 전이 규칙 위반",
    "OPINION_LEAK": "Generator 의견 포함",
    "BUDGET_EXCEED": "토큰 예산 초과",
}
```

### 3. FederatedBudget 기반 비용 관리

**적용 대상**: 새 파일 `budget_tracker.py`

스프린트별 토큰 사용량 추적 + 하드 상한:
```python
class SprintBudget:
    def __init__(self, max_tokens: int):
        self.ceiling = max_tokens
        self.spent = 0

    def can_spend(self, tokens: int) -> bool:
        return self.spent + tokens <= self.ceiling

    def record(self, tokens: int):
        self.spent += tokens
        if self.spent > self.ceiling * 0.9:
            emit_warning("budget_warning", self.spent, self.ceiling)
```

### 4. HMAC 서명 감사 로그

**적용 대상**: `eval_dispatch.py` 평가 로그

```python
import hmac, hashlib, json
def append_audit_log(entry: dict, secret: bytes):
    payload = json.dumps(entry, sort_keys=True)
    signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    entry["_signature"] = signature
    with open("audit_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
```

### 5. 어댑터 레지스트리 패턴 (평가자 플러그인화)

**적용 대상**: `evaluators/` 디렉토리

```python
class EvaluatorAdapter(Protocol):
    def evaluate(self, code: str, contract: str) -> EvalResult: ...

class EvaluatorRegistry:
    _adapters: dict[str, EvaluatorAdapter] = {}

    @classmethod
    def register(cls, name: str, adapter: EvaluatorAdapter):
        cls._adapters[name] = adapter

    @classmethod
    def get(cls, name: str) -> EvaluatorAdapter:
        return cls._adapters[name]
```

---

## AHOY 개선 제안 Top 3

### 1. 컴플라이언스 위반 분류 로깅 시스템

**구현 방향**: Hook의 차단 이벤트를 4종(SCOPE_ESCAPE/STATE_SKIP/OPINION_LEAK/BUDGET_EXCEED) 이상으로 분류하고 `sprint_violations.jsonl`에 누적 기록. 이 데이터로 반복 위반 패턴을 분석하여 Hook 규칙 자동 강화.

**변경 파일**:
- `hooks/pre_tool_use.py` — 위반 분류 로직 추가
- `hooks/post_tool_use.py` — 위반 분류 로직 추가
- 신규 `violation_logger.py` — JSONL 기록 + 패턴 분석
- `eval_dispatch.py` — 위반 통계를 평가 컨텍스트에 포함

### 2. 스프린트 토큰 예산 관리 시스템

**구현 방향**: 스프린트별 토큰 사용량을 추적하고, 예산의 90% 도달 시 경고, 100% 도달 시 rework 강제 종료. handoff 문서에 비용 효율 데이터 포함.

**변경 파일**:
- 신규 `budget_tracker.py` — 토큰 추적 + 하드 상한
- `eval_dispatch.py` — 평가 호출 시 토큰 기록
- `hooks/pre_tool_use.py` — 예산 초과 시 차단

### 3. 평가자 어댑터 레지스트리 + HMAC 감사 로그

**구현 방향**: `evaluators/` 디렉토리에 인터페이스 기반 어댑터(CodexAdapter, GeminiAdapter) 구현. 모든 평가 요청/응답을 HMAC 서명된 JSONL 로그에 기록하여 사후 감사 가능.

**변경 파일**:
- 신규 `evaluators/__init__.py` — 레지스트리 + Protocol
- 신규 `evaluators/codex_adapter.py` — Codex 평가 구현
- 신규 `evaluators/gemini_adapter.py` — Gemini 평가 구현
- `eval_dispatch.py` — 레지스트리 기반 평가자 호출 + 감사 로그
- 신규 `audit_logger.py` — HMAC 서명 JSONL 로그
