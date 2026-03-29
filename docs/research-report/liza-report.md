# Liza (liza-mas/liza) 분석 리포트

> 분석일: 2026-03-28 (8차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Liza — Disciplined Multi-Agent Coding System |
| GitHub URL | https://github.com/liza-mas/liza |
| 스타 | 86 |
| 최근 커밋 | 2026-03-28 (활발, v0.4.0+ 자기 자신으로 개발) |
| 라이선스 | Apache 2.0 |
| 언어 | Go (20k LOC) + 60k 줄 테스트 |
| 핵심 키워드 | 적대적 페어링, 행동 계약, Go 결정론적 감독, YAML 블랙보드, 9 에이전트 역할 |

## 핵심 아키텍처

Liza는 **"첫 패스에서 올바르게 하기"에 최적화된 하드닝 멀티 에이전트 코딩 시스템**으로, 결정론적 Go 감독자가 LLM 에이전트를 격리된 Git Worktree에서 래핑하는 하이브리드 구조를 사용한다.

### 핵심 설계 원칙

> "판단(LLM 영역)과 기계적 강제(코드 영역)의 분리"

- **Go CLI + Supervisor**: 결정론적 오케스트레이션 (LLM에 의존하지 않는 강제)
- **YAML Blackboard** (state.yaml): 조율된 워크플로우를 위한 공유 상태
- **MCP Tools**: 결정론적 Go 구현
- **Git Worktrees**: 태스크별 격리 작업 공간
- **행동 계약**: 55+ 문서화된 실패 모드와 대응 방안

### 9개 에이전트 역할 (적대적 페어링)

**명세 단계 (Specification Phase):**
- Orchestrator (목표를 태스크로 분해)
- Epic Planner ↔ **Epic Plan Reviewer** (페어 검증)
- US Writer ↔ **US Reviewer** (페어 검증)

**코딩 단계 (Coding Phase):**
- Orchestrator (진행 기반 재범위 조정)
- Code Planner ↔ **Code Plan Reviewer** (페어 검증)
- Coder ↔ **Code Reviewer** (페어 검증)

**계획 중:** Sprint Analyzer, Architect/Architecture Reviewer, Security Auditor 페어

모든 활동에 **Doer/Reviewer 페어**가 존재하여 각 산출물이 독립 검증을 거침.

### 2단계 워크플로우

```
명세 단계 (Specification Phase)
  Epic Planning → Epic Review → US Writing → US Review
                    ↓
              [liza proceed]
                    ↓
코딩 단계 (Coding Phase)
  Code Planning → Code Plan Review → Coding → Code Review
```

에이전트는 스프린트 내에서 완전 자율. 사용자는 스프린트 사이에서 방향 제어.

### 상태머신 (43+ 전이 규칙)

**태스크 내 흐름:**
```
initial → executing → submitted → reviewing → approved → MERGED
           ↑                          ↓
           └────── rejected ──────────┘
```

**터미널 상태:** BLOCKED, INTEGRATION_FAILED, SUPERSEDED, ABANDONED

**스프린트 간 전이:** `liza proceed`가 하류 태스크 생성 (epic→us, us→coding, code-plan→coding)

### Hook 및 가드레일

1. **실행 전 체크포인트**: 에이전트가 의도, 수정 파일, 검증 계획을 문서화한 후 태스크 수행
2. **TDD 게이트**: 테스트 통과 없이 머지 불가
3. **워크트리 머지 검증**: 자동 병합 충돌 검사
4. **코드 리뷰 형식 검증**: 구조화된 리뷰 제출 형식 강제
5. **승인 요청 메커니즘**: 행동 전 구조화된 이유 제시 필수
6. **서킷 브레이커**: 루프/반복 실패 패턴 감지 → 자동 스프린트 체크포인트

### 행동 계약 (Behavioral Contract)

55+ 문서화된 실패 모드와 각각에 대한 구체적 대응 방안. 일부 게이트는 "절대 양보하지 않는" 기계적 강제, 나머지는 점진적 퇴화(graceful degradation).

### 크래시 복구

- `recover-agent <id>`: 에이전트 복구
- `recover-task`: 태스크 복구
- 멱등성(idempotent) 보장

### 멀티 모델 지원

CLI 래핑 방식 (API 아닌 기존 구독 활용):
- Claude Opus 4.x: 완전 호환 (참조 프로바이더)
- GPT-5.x-Codex: 완전 호환
- Kimi 2.5: 호환 (약간 약함)
- Mistral Devstral-2: 부분 호환
- Gemini 2.5 Flash: 비호환

## AHOY 비교 분석

### AHOY보다 나은 점

1. **적대적 페어링 모든 단계에 적용**: AHOY는 생성-평가 분리만 있지만, Liza는 기획, 명세, 코딩, 리뷰 모든 단계에 Doer/Reviewer 페어를 적용. 기획 단계부터 품질 확보
2. **55+ 실패 모드 행동 계약**: AHOY의 Hook 규칙보다 훨씬 포괄적. 55개 이상의 알려진 실패 모드에 대한 문서화된 대응 전략
3. **명세 단계 존재**: AHOY는 planned→contracted 직행. Liza는 Epic Planning→US Writing 단계를 거쳐 요구사항을 체계적으로 정제
4. **결정론적 Go 감독자**: LLM 프롬프트가 아닌 Go 코드로 규칙 강제. 우회 불가능성이 AHOY의 Hook보다 강력
5. **YAML Blackboard 공유 상태**: 모든 에이전트가 단일 state.yaml을 통해 상태 동기화. AHOY의 issues.json보다 풍부한 메타데이터 (의도, 검증 계획, 이벤트 히스토리)
6. **TDD 게이트 강제**: 테스트 통과를 머지 전제조건으로 기계적 강제. AHOY는 테스트 실행을 평가자에게 위임
7. **실행 전 의도 문서화**: 에이전트가 코딩 전에 의도, 수정 파일, 검증 계획을 선언. AHOY에는 이 사전 체크포인트 없음
8. **서킷 브레이커 + 크래시 복구**: 루프 감지와 멱등 복구. AHOY는 rework 3회 제한만 존재

### AHOY가 더 나은 점

1. **외부 모델 평가 (진정한 외부 시선)**: Liza의 Reviewer는 같은 시스템 내 에이전트. AHOY는 완전히 다른 모델(Codex/Gemini)이 평가하여 자기평가 편향을 더 강하게 차단
2. **다중 모델 필수 컨센서스**: Liza는 단일 Reviewer. AHOY는 2+ 모델의 합의 필요
3. **Generator 의견 strip**: Liza는 Doer 출력을 그대로 Reviewer에게 전달. AHOY는 주관적 판단을 기계적으로 제거
4. **파일 소유권 분리**: Liza는 모든 에이전트가 state.yaml에 쓸 수 있음 (Go 감독자 통해). AHOY는 issues.json 쓰기를 eval_dispatch.py만 허용
5. **컨텍스트 리셋**: 3 스프린트마다 강제 세션 리셋. Liza는 긴 세션에서 컨텍스트 오염 위험
6. **단순성**: AHOY는 4상태 FSM으로 이해하기 쉬움. Liza는 9 역할 + 43+ 전이 규칙으로 복잡도 높음

### 배울 만한 구체적 아이디어

1. **실행 전 의도 선언 (Pre-Execution Intent Declaration)**
   - 구현: generated 진입 전 Generator가 `.ahoy/intent.md`에 수정 파일 목록, 접근 방법, 검증 계획 작성. Hook으로 강제
   - 효과: Generator의 계획 없는 코딩 방지, 평가 시 의도 vs 결과 비교 가능

2. **55+ 실패 모드 카탈로그 AHOY 버전**
   - 구현: `.ahoy/failure_modes.yaml`에 알려진 실패 모드와 대응 방안 문서화. 예: "Generator가 테스트 없이 pass 요청", "평가자가 모든 것을 pass", "rework에서 같은 문제 반복"
   - 효과: 새로운 AHOY 사용자의 학습 곡선 단축, Hook 규칙 설계 가이드

3. **명세 정제 단계 (Specification Phase)**
   - 구현: planned → **specifying** → contracted 사이에 단계 삽입. specifying에서 LLM이 계약 초안 작성 → 별도 LLM이 리뷰 → 리뷰 통과 후 contracted
   - 효과: contract.md 품질 향상, 모호한 요구사항 조기 제거

4. **Go 기반 결정론적 검증 레이어**
   - 구현: Hook 규칙의 핵심 검증을 Python이 아닌 컴파일 언어 바이너리로 분리. 빠른 실행 + 우회 불가
   - 효과: Hook 실행 속도 향상, 보안성 강화

5. **서킷 브레이커 패턴 강화**
   - 구현: rework 중 동일 이슈 3회 반복 감지 → 자동 스프린트 체크포인트 + handoff 생성 + 사용자 개입 요청
   - 효과: 무한 rework 루프 조기 탈출

## AHOY 개선 제안 Top 3

### 1. 실행 전 의도 선언 (Pre-Execution Intent Declaration)
- **현재**: Generator가 즉시 코딩 시작
- **개선**: contracted→generated 전이 시 Generator가 먼저 `.ahoy/intent.md`를 작성해야 함. 내용: 수정 대상 파일, 구현 접근법, 예상 테스트, 위험 요소. PostToolUse Hook으로 intent.md 작성 완료 검증 후 실제 코딩 허용
- **파일**: PreToolUse Hook (코딩 도구 차단 → intent.md 존재 확인), intent.md 템플릿
- **효과**: Generator의 계획 없는 코딩 방지, 평가 시 의도-결과 갭 분석 가능, rework 감소

### 2. 명세 정제 단계 (Specification Refinement Phase)
- **현재**: planned → contracted 직접 전이 (사용자가 수동으로 contract.md 작성)
- **개선**: planned → **specifying** → contracted 3단계. specifying에서 LLM이 planned의 요구사항을 구체적 contract.md 초안으로 변환. 별도 평가 모델이 contract 품질(완전성, 테스트 가능성, 모호성) 검증. 검증 통과 시 contracted 전이
- **파일**: 상태머신에 `specifying` 상태 추가, `contract_evaluator.py` 신규 (계약 품질 평가)
- **효과**: contract.md 품질 보증, 모호한 요구사항으로 인한 rework 50% 감소 기대

### 3. 실패 모드 카탈로그 및 자동 감지
- **현재**: rework 3회 제한만으로 실패 대응
- **개선**: `.ahoy/failure_modes.yaml`에 30+ 알려진 실패 패턴 정의. 예: `repeated_same_issue` (동일 이슈 반복), `placeholder_injection` (TODO/placeholder 삽입), `scope_creep` (범위 이탈), `test_skip` (테스트 회피). 각 패턴에 감지 로직 + 대응 액션(경고/차단/에스컬레이션) 매핑. Hook에서 실시간 패턴 매칭
- **파일**: `.ahoy/failure_modes.yaml` (패턴 정의), Hook 확장 (패턴 매칭 엔진)
- **효과**: 알려진 실패 모드 자동 감지 → rework 효율 향상, 새로운 실패 모드 지속 추가 가능
