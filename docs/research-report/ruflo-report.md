# Ruflo 분석 리포트

> 분석일: 2026-03-28 (4차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Ruflo v3.5 |
| GitHub URL | https://github.com/ruvnet/ruflo |
| 스타 | 27,400 |
| 포크 | 3,000 |
| 최근 커밋 | 활발 (main branch) |
| 라이선스 | MIT |
| 언어 | Python + WASM |

## 핵심 아키텍처

### 구조 개요

Ruflo는 **프로덕션 레디 다중 에이전트 AI 오케스트레이션 플랫폼**으로, Claude Code 네이티브 통합을 지원하는 대규모 시스템이다. 계층적 여왕벌(Queen)-일벌(Worker) 구조로 에이전트 군집을 관리한다.

```
Queen Agents (전략/전술/적응)
  → Worker Agents (8종 전문 역할)
    → Task Decomposition (5 도메인)
      → Consensus (Raft/BFT/Gossip/CRDT)
        → Learning Loop (RETRIEVE→JUDGE→DISTILL→CONSOLIDATE→ROUTE)
```

### 여왕벌-일벌 계층 구조

**Queen 유형 (3종)**:
| 유형 | 역할 |
|------|------|
| Strategic | 장기 계획 수립 |
| Tactical | 실행 조율 |
| Adaptive | 런타임 최적화 |

**Worker 유형 (8종)**:
researcher, coder, analyst, tester, architect, reviewer, optimizer, documenter

### 컨센서스 프로토콜 (4종)

| 프로토콜 | 특성 |
|---------|------|
| **Raft** | 리더 기반 합의, 빠른 수렴 |
| **BFT (Byzantine Fault Tolerant)** | f < n/3 내결함성, 가장 엄격 |
| **Gossip** | 분산 전파 기반, 대규모 확장 |
| **CRDT** | 충돌 없는 복제 데이터, 오프라인 지원 |

### RuVector 지능 레이어

| 컴포넌트 | 역할 |
|---------|------|
| SONA | 자기 최적화 신경 아키텍처 (서브밀리초 적응) |
| EWC++ | 탄력적 가중치 통합 (망각 방지) |
| Flash Attention | 2.49-7.47x 어텐션 가속 |
| HNSW | 계층적 벡터 검색 (150-12,500x 가속) |
| ReasoningBank | 패턴 저장소 (RETRIEVE→JUDGE→DISTILL) |
| LoRA/MicroLoRA | 128x 파라미터 압축 |
| 9종 RL 알고리즘 | Q-Learning, SARSA, A2C, PPO, DQN, Decision Transformer |

### Hook 시스템 (27종)

- Pre/Post 태스크 실행 Hook
- 컨텍스트 트리거 백그라운드 워커 (12종)
- 학습 루프 Hook (RETRIEVE, JUDGE, DISTILL, CONSOLIDATE, ROUTE)
- 파일 변경 감지 + 패턴 인식 트리거

### 성능 지표

| 메트릭 | 수치 |
|--------|------|
| 벡터 검색 | ~61μs/쿼리, 16,400 QPS |
| 태스크 라우팅 정확도 | 89% |
| 스웜 성공률 | 100% (권장 설정) |
| 메모리 압축 | 3.92x (Int8 양자화) |
| Agent Booster (WASM) | <1ms (API 대비 352x 빠름) |
| 토큰 최적화 | 30-50% 절감 |

## AHOY와의 비교

### AHOY보다 나은 점

| 영역 | Ruflo | AHOY |
|------|-------|------|
| **규모** | 100+ 전문 에이전트, 8종 역할 | Generator 1개 + Evaluator 2개 |
| **컨센서스 다양성** | 4종 프로토콜 (Raft/BFT/Gossip/CRDT) | 단순 다수결 (하나라도 fail→전체 fail) |
| **학습 루프** | 5단계 패턴 학습 + 강화학습 | 실패 패턴 학습 없음 |
| **토큰 최적화** | 30-50% 절감 (컨텍스트 압축 + 캐싱) | 토큰 최적화 없음 |
| **WASM 가속** | 단순 작업 API 미호출 (<1ms) | 모든 작업 API 호출 |
| **벡터 메모리** | 공유 벡터 스토어 + 지식 그래프 | handoff 문서 기반 텍스트 |
| **멀티 프로바이더** | Claude/GPT/Gemini/Cohere/Ollama 자동 폴백 | Codex + Gemini 고정 |
| **MCP 네이티브** | MCP 서버로 Claude Code 직접 통합 | 커스텀 Hook 기반 |
| **보안** | AIDefence (프롬프트 주입 방어 + 입력 검증) | 파일 소유권 분리만 |

### AHOY가 더 나은 점

| 영역 | AHOY | Ruflo |
|------|------|-------|
| **Generator-Evaluator 구조적 분리** | 생성과 평가를 다른 모델로 강제 분리 | Worker 중 reviewer가 있지만 같은 시스템 내부 |
| **하드 차단** | Hook으로 상태 전이 규칙 우회 불가 | 소프트 컨센서스 (수렴 기반, 강제 없음) |
| **파일 소유권 분리** | issues.json 쓰기 권한 격리 | 공유 벡터 스토어 (접근 제어 미상) |
| **주관적 판단 제거** | gen_report에서 의견 strip | 의견 필터링 메커니즘 언급 없음 |
| **계약 기반 개발** | contract.md가 공통 참조점 | 태스크 분해는 있으나 계약 문서 없음 |
| **단순성/투명성** | 상태머신이 명확하고 감사 가능 | 복잡한 RL/벡터/WASM 레이어로 블랙박스 위험 |
| **아첨 편향 방지** | 외부 모델 사용으로 자기평가 편향 차단 | 같은 시스템 내 reviewer로 편향 가능성 |

### 복잡도 vs 효과 트레이드오프

Ruflo는 27,400 스타의 대규모 프로젝트이지만, AHOY의 핵심 강점인 **"구조적으로 편향을 차단"**하는 설계 철학과는 다른 접근을 취한다. Ruflo는 **"더 많은 에이전트, 더 많은 기능"**으로 품질을 높이려 하고, AHOY는 **"더 엄격한 제약"**으로 품질을 보장하려 한다.

## 배울 만한 구체적 아이디어

### 1. 학습 루프 (Learning Loop)
```python
# AHOY에 적용: 실패 패턴 축적 시스템
class SprintLearningLoop:
    def retrieve(self, sprint_context):
        """과거 유사 스프린트의 실패 패턴 검색"""
    def judge(self, patterns):
        """패턴 유효성 평가"""
    def distill(self, valid_patterns):
        """일반화 가능한 규칙 추출"""
    def consolidate(self, rules):
        """contract.md 자동 참조 삽입"""
    def route(self, sprint):
        """패턴 기반 평가 강도 자동 조절"""
```

### 2. 토큰 최적화
- 평가 시 컨텍스트 압축으로 비용 절감
- 미변경 파일 결과 캐싱
- 단순 검증(린트, 포맷)은 API 미호출로 로컬 처리

### 3. 멀티 프로바이더 자동 폴백
```python
# eval_dispatch.py에 적용
EVAL_PROVIDERS = [
    {"model": "codex", "priority": 1},
    {"model": "gemini", "priority": 2},
    {"model": "claude-haiku", "priority": 3, "fallback": True},
]
# 연속 2회 실패 시 다음 프로바이더로 자동 전환
```

---

## AHOY 개선 제안 Top 3

### 1. 5단계 학습 루프 (Sprint Learning Loop) 도입
- **현재**: 실패한 스프린트의 교훈이 다음 스프린트에 자동 전달되지 않음
- **개선**: RETRIEVE→JUDGE→DISTILL→CONSOLIDATE→ROUTE 학습 파이프라인
- **구현 방향**:
  - `sprint_memory/` 디렉토리에 실패 패턴 JSON 축적
  - `sprint_memory/patterns.json` — `{pattern_id, failure_type, context, frequency, last_seen}`
  - contracted 상태 진입 시 유사 패턴 자동 검색 → contract.md에 `## 주의사항` 자동 삽입
  - 3회 이상 반복된 패턴은 PreToolUse Hook 규칙으로 자동 승격
  - 효과: rework 횟수 감소, 반복 실패 방지

### 2. 토큰 최적화 레이어
- **현재**: 평가 시 전체 파일을 매번 외부 모델에 전송
- **개선**: 컨텍스트 압축 + 캐싱으로 평가 비용 30-50% 절감
- **구현 방향**:
  - `eval_dispatch.py`에 `compress_context()` 함수 추가
  - 미변경 파일 해시 캐시 (`eval_cache/` 디렉토리)
  - rework 시 변경된 파일 + 변경 diff만 전송
  - 린트/포맷 검사는 로컬에서 사전 실행 (API 호출 불필요)
  - 캐시 히트율/비용 절감 통계 스프린트 로그에 기록

### 3. 멀티 프로바이더 폴백 체인
- **현재**: Codex/Gemini 중 하나가 장애 시 스프린트 중단 위험
- **개선**: 평가 모델 폴백 체인 + Circuit Breaker
- **구현 방향**:
  - `eval_config.json`에 프로바이더 우선순위 목록 + 폴백 규칙
  - 연속 N회 실패 시 자동 다음 프로바이더 전환
  - 폴백 모델 사용 시 `issues.json`에 `evaluator_fallback: true` 플래그
  - 주 프로바이더 복구 시 자동 복귀 (health check 주기 설정)
  - 모든 프로바이더 장애 시 스프린트 일시정지 (데이터 손실 방지)
