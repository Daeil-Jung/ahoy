# EvoAgentX (EvoFSM) 분석 리포트

> 분석일: 2026-03-28 (6차)

## 프로젝트 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | EvoAgentX |
| URL | https://github.com/EvoAgentX/EvoAgentX |
| 스타 | ~2,500+ |
| 최근 활동 | 활발 (2025-05 출시, 지속 업데이트) |
| 라이선스 | Apache 2.0 |
| 관련 논문 | EvoFSM (arxiv 2601.09465, 2026-01) |

## 핵심 아키텍처

### 자기진화 에이전트 생태계

EvoAgentX는 정적 프롬프트 체이닝이나 수동 워크플로우 오케스트레이션을 넘어, **자기진화(Self-Evolving) 에이전트 생태계**를 구축하는 프레임워크다. 에이전트가 반복적 피드백 루프를 통해 구축, 평가, 최적화된다.

### EvoFSM 핵심 개념

EvoFSM은 태스크 해결을 **유한상태머신(FSM)**으로 모델링하여 제어 가능한 진화를 달성한다:

1. **Flow-Skill 분리**: 거시적 Flow(상태 전이 로직)와 미시적 Skill(상태별 행동)을 분리하여 독립적 최적화
2. **제약된 진화 연산**: 자유로운 재작성 대신 소수의 제한된 FSM 연산으로 진화 (상태 추가/제거, 전이 수정)
3. **Critic 메커니즘**: 비평자가 FSM 진화를 가이드하여 목적 지향적 개선
4. **자기진화 메모리**: 성공 궤적을 재사용 가능한 패턴으로 증류하여 축적

### 최적화 알고리즘

- **TextGrad**: 그래디언트 기반 프롬프트/추론 체인 최적화
- **MIPRO**: 모델 비의존 반복 프롬프트 최적화 (블랙박스 평가 + 적응형 재순위)
- **AFlow**: 몬테카를로 트리 탐색(MCTS) 기반 에이전트 워크플로우 진화

### 벤치마크 통합

HotPotQA (다중 홉 QA), MBPP (코드 생성), MATH (추론) 등 표준 벤치마크에서 평가 및 최적화 지원.

## AHOY와의 비교

### AHOY보다 나은 점

1. **자기진화 상태머신**: AHOY의 스프린트 상태머신은 고정된 전이 규칙을 따르지만, EvoFSM은 FSM 자체가 진화한다. 실패 패턴에 따라 상태 전이 로직이 자동 최적화됨
2. **Critic 기반 가이드 진화**: AHOY의 평가자는 pass/fail만 판정하지만, EvoFSM의 Critic은 "어떻게 개선할지"까지 가이드하는 방향성 피드백 제공
3. **성공 궤적 메모리**: 과거 성공 패턴을 재사용 가능한 형태로 증류하여 축적. AHOY의 sprint_memory보다 체계적
4. **Flow-Skill 독립 최적화**: 워크플로우 구조와 개별 스킬을 독립적으로 최적화. AHOY는 이 구분이 없음
5. **다중 최적화 알고리즘**: TextGrad/MIPRO/AFlow 등 여러 최적화 전략 플러그인 지원

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리**: EvoAgentX는 자기평가(self-assessment) 기반. AHOY의 외부 모델 평가로 편향 차단하는 아키텍처가 더 견고
2. **다중 모델 필수 컨센서스**: EvoAgentX는 단일 Critic. AHOY의 2+ 외부 모델 합의 필수는 더 높은 평가 신뢰도
3. **Hook 기반 하드 차단**: EvoAgentX의 진화는 소프트 제약(최적화 목표). AHOY의 PreToolUse/PostToolUse Hook은 우회 불가능한 하드 차단
4. **파일 소유권 분리**: EvoAgentX에는 파일 쓰기 권한 분리 개념이 없음
5. **Generator 의견 strip**: EvoAgentX의 Critic은 에이전트와 동일 시스템 내. AHOY의 주관적 판단 제거 메커니즘 부재

## 배울 만한 구체적 아이디어

### 1. 적응형 상태 전이 (Adaptive FSM)
- **현재 AHOY**: `planned→contracted→generated→passed` 고정 전이
- **제안**: 실패 패턴 통계에 따라 전이 규칙 자동 조정. 예: contract 품질 문제가 반복되면 `planned→prd→contracted` 중간 단계 자동 삽입
- **구현 위치**: `hooks/` 디렉토리에 `adaptive_transition.py` 추가

### 2. Critic 피드백 강화 (Directional Feedback)
- **현재 AHOY**: eval_dispatch.py가 pass/fail + issue 목록 전달
- **제안**: 각 issue에 "개선 방향 힌트"를 구조적으로 포함. `{"issue": "...", "direction": "...", "priority": "high"}`
- **구현 위치**: `eval_dispatch.py` 평가 프롬프트에 방향성 피드백 필드 추가

### 3. 성공 궤적 증류 (Trajectory Distillation)
- **현재 AHOY**: handoff 문서로 컨텍스트 인계
- **제안**: passed 스프린트의 (contract → 생성 코드 → 평가 결과) 삼중 쌍을 패턴으로 추출, `sprint_patterns/` 디렉토리에 축적
- **구현 위치**: `sprint_patterns/` 디렉토리 신설, passed 후 자동 패턴 추출 스크립트

## AHOY 개선 제안 Top 3

### 1. 적응형 상태 전이 규칙 (Adaptive State Transitions)
- **파일**: `hooks/adaptive_transition.py` (신규), `settings.json`에 `adaptive_mode: true` 옵션
- **구현**: 최근 N 스프린트의 rework 원인 통계 → 특정 패턴 반복 시 중간 검증 단계 자동 삽입 (예: contract 모호성 → prd 단계 자동 활성화)
- **효과**: 반복적 실패 패턴을 시스템이 자동 학습하여 예방

### 2. 방향성 피드백 스키마 (Directional Feedback Schema)

> **v0.2.0 구현 완료** — `eval_dispatch.py` suggestion 필드로 구체적 파일/위치/수정 방향 포함. consensus merge 시 보존

- **파일**: `eval_dispatch.py` 평가 프롬프트 수정
- **구현**: issues.json 스키마에 `"improvement_hint"` 필드 추가. 평가자에게 "무엇이 문제인지"뿐 아니라 "어떻게 고쳐야 하는지" 힌트 생성 강제
- **효과**: Generator의 rework 효율 향상, rework 횟수 감소 기대

### 3. 성공 패턴 메모리 시스템 (Sprint Pattern Memory)
- **파일**: `sprint_patterns/` 디렉토리 (신규), `post_sprint_hook.py` (신규)
- **구현**: passed 스프린트 완료 시 (contract 유형, 코드 패턴, 평가 통과 요인)을 YAML로 자동 추출. 새 스프린트의 contract.md 생성 시 유사 패턴 자동 참조
- **효과**: 스프린트 학습 축적, 반복 실수 방지, contract 품질 향상
