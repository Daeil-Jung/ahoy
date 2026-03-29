# wshobson/agents 분석 리포트

> 분석일: 2026-03-29

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | wshobson/agents |
| URL | https://github.com/wshobson/agents |
| 스타 | 31,400+ |
| 최근 활동 | 2026-03 활발한 커밋 |
| 라이선스 | MIT |
| 핵심 키워드 | 112 에이전트, 72 플러그인, Agent Teams, Conductor, TDD, 멀티 모델 |

## 핵심 아키텍처

### 구조

112개 특화 에이전트, 16개 멀티 에이전트 워크플로우 오케스트레이터, 146개 스킬, 79개 개발 도구를 72개 단일 목적 플러그인으로 조직한 Claude Code 생태계.

### 5가지 워크플로우

1. **Git Workflow**: 커밋, PR, 브랜치 관리 자동화
2. **Full-Stack Workflow**: 프론트엔드+백엔드 통합 개발
3. **TDD Workflow**: 테스트 주도 개발 강제 (`/conductor:implement` → 검증 체크포인트)
4. **Conductor**: Context-Driven Development — 컨텍스트를 코드와 동등한 산출물로 관리. Context → Spec & Plan → Implement
5. **Agent Teams**: 멀티 에이전트 병렬 오케스트레이션 (Claude Code 실험 기능 활용)

### Agent Teams 프리셋

| 프리셋 | 구성 | 기능 |
|--------|------|------|
| review | 3 리뷰어 | 보안/성능/아키텍처/테스트/접근성 5차원 병렬 코드 리뷰 |
| debug | 3 조사자 | 경쟁 가설 3개 → 증거 수집 → 근본 원인 합산 |
| feature | N 구현자 | 작업 분해 → 파일 소유권 경계 → 병렬 구현 |
| security | 4 리뷰어 | OWASP/인증/공급망/시크릿 4관점 보안 리뷰 |

### 모델 전략

- Planning Phase: Sonnet
- Execution Phase: Haiku
- Review Phase: Sonnet

## AHOY와 비교

### AHOY보다 나은 점

1. **규모와 범위**: 112개 에이전트, 72개 플러그인이라는 압도적 커버리지. AHOY는 Generator+Evaluator 2역할에 집중.
2. **파일 소유권 기반 병렬 구현**: feature 팀에서 "같은 파일을 두 구현자에게 할당하지 않음" 규칙으로 병렬 작업 시 충돌 방지. AHOY는 단일 Generator라 병렬 생성 불가.
3. **경쟁 가설 디버깅**: debug 팀에서 3개 가설을 독립 조사 후 합산. 단일 관점 편향 감소.
4. **Conductor의 Context-as-Artifact**: 컨텍스트 자체를 버전 관리 가능한 산출물로 취급. AHOY의 handoff 문서보다 구조화됨.
5. **모델 계층화 전략**: 단계별 최적 모델 배치 (Sonnet→Haiku→Sonnet)로 비용 효율화. AHOY는 Generator=Claude, Evaluator=외부 모델로 역할만 분리.

### AHOY가 더 나은 점

1. **Generator-Evaluator 물리적 분리**: wshobson/agents의 리뷰어는 동일 Claude Code 세션 내 서브에이전트. AHOY는 eval_dispatch.py가 완전히 별도 프로세스로 외부 모델을 호출 → 자기평가 편향 원천 차단.
2. **any fail → final fail 결정론적 컨센서스**: wshobson/agents의 리뷰는 "통합 보고서" 수준. AHOY는 하나라도 fail이면 전체 fail인 엄격한 규칙.
3. **파일 소유권 강제 (Hook 수준)**: AHOY는 `validate_harness.py`가 issues.json 쓰기를 셸 수준에서 차단. wshobson/agents는 "파일 소유권 경계" 문서 수준 안내만.
4. **Generator 의견 제거**: AHOY의 `strip_generator_opinions()`은 기계적 편향 차단. wshobson/agents에는 동등 기능 없음.
5. **상태머신 기반 스프린트**: AHOY의 planned→contracted→generated→passed 사이클 + rework 한도. wshobson/agents는 상태머신 없이 워크플로우 명령으로 진행.
6. **Hook 기반 하드 차단**: AHOY의 PreToolUse/PostToolUse Hook이 상태 전이 규칙 강제. wshobson/agents는 소프트 가이드.

## 배울 만한 구체적 아이디어

### 1. 경쟁 가설 기반 Rework 전략

현재 AHOY는 rework 시 동일 Generator가 동일 관점으로 재시도. wshobson/agents의 debug 팀처럼 **rework 시 3개 대안 접근법을 병렬로 시도**하면 수렴 속도 향상 가능.

**적용 방향**: `eval_dispatch.py`에서 rework 2회차부터 Generator에게 "이전 접근법과 다른 전략을 사용하라"는 지시를 주입. 또는 T4-1 루프 감지와 연계하여 유사도 80%+ 시 전략 변경 강제.

### 2. 모델 계층화 비용 최적화

Conductor의 Planning(Sonnet)→Execution(Haiku)→Review(Sonnet) 패턴을 AHOY에 적용:
- contracted 단계 (계약 작성): 고성능 모델
- generated 단계 (코드 생성): 비용 효율 모델
- 평가: 외부 고성능 모델 (현재 유지)

**적용 방향**: `skills/ahoy-gen/SKILL.md`에 모델 추천 가이드 추가, 또는 contract.md에 `model_tier` 필드.

### 3. 플러그인 단위 조합 아키텍처

72개 단일 목적 플러그인의 "토큰 최소, 조합 가능" 설계 철학. 현재 AHOY는 모놀리식 스킬 파일.

**적용 방향**: 장기적으로 AHOY 기능을 독립 플러그인으로 분리 가능성 검토 (예: eval-plugin, guard-plugin, sprint-plugin).

---

## AHOY 개선 제안 Top 3

### 1. Rework 전략 다양화 (T4-1 확장)

**현재**: rework 시 동일 접근법 재시도 → 루프 위험.
**제안**: rework 2회차에 Generator 프롬프트에 "이전 시도와 다른 구현 전략" 지시 자동 삽입. 이전 gen_report.md의 접근법 요약을 "회피해야 할 패턴"으로 전달.
**변경 대상**: `eval_dispatch.py` (rework 피드백 구성), `skills/ahoy-gen/SKILL.md` (대안 전략 지시)

### 2. 평가 관점 다차원화 (T2-2 구체화)

**현재**: 외부 모델 2개가 동일 프롬프트로 평가.
**제안**: wshobson/agents의 5차원 리뷰(보안/성능/아키텍처/테스트/접근성)에서 영감. 평가 프롬프트에 모델별 **관점 할당** — 모델 A는 "정확성+테스트 커버리지", 모델 B는 "보안+엣지케이스". 다른 관점에서의 합의가 동일 관점 합의보다 신뢰성 높음.
**변경 대상**: `eval_dispatch.py:92-130` (build_eval_prompt에 관점 파라미터 추가)

### 3. Context-as-Artifact 도입

**현재**: handoff 문서는 3 스프린트마다 수동 생성.
**제안**: Conductor의 "컨텍스트는 코드와 동등한 산출물" 개념 적용. 매 스프린트 완료 시 자동으로 `context_snapshot.json` 생성 (현재 상태, 결정 이력, 미해결 이슈). handoff 시 이를 기반으로 자동 인계 문서 생성.
**변경 대상**: `validate_harness.py` (passed 전이 시 스냅샷 저장), handoff 템플릿 추가
