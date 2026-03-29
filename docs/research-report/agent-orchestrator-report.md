# Composio Agent Orchestrator 분석 리포트

> 분석일: 2026-03-27

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Agent Orchestrator (Composio) |
| URL | https://github.com/ComposioHQ/agent-orchestrator |
| 스타 | 5.5k |
| 언어 | TypeScript (91.1%) |
| 최근 커밋 | 2026-03-26 (v0.2.1) |
| 최근 활동 | 매우 활발 |

## 핵심 아키텍처

### 8슬롯 플러그인 아키텍처
모든 주요 컴포넌트가 교체 가능한 모듈식 설계:

| 컴포넌트 | 기본값 | 대안 |
|----------|--------|------|
| Runtime | tmux | docker, k8s, process |
| Agent | claude-code | codex, aider, opencode |
| Workspace | worktree | clone |
| Tracker | github | linear |
| Notifier | desktop | slack, composio, webhook |

### 5단계 워크플로우
1. 대시보드가 오케스트레이터 에이전트 실행
2. 에이전트가 이슈별 격리된 git worktree에서 개별 워커 스폰
3. 에이전트가 자율적으로 코드 변경 + 테스트 실행
4. CI 실패/리뷰 코멘트를 에이전트에게 피드백 라우팅
5. 판단 필요한 결정만 인간이 개입

### 자율 운영
- **CI 처리**: 실패 로그 수신 → 자율 수정 구현 (재시도 제한: 기본 2회)
- **코드 리뷰**: 리뷰어 코멘트를 에이전트에게 라우팅, 에스컬레이션 임계값 초과 시 인간 개입
- **머지 충돌 해결**: git worktree 격리로 병렬 에이전트 간 충돌 없이 동시 작업

### 실행 모델
이슈마다 독립 에이전트 + 격리된 git worktree → 수십 개 동시 개선 가능. `localhost:3000` 통합 대시보드로 감독.

## AHOY와 비교

### AHOY보다 나은 점
1. **플러그인 아키텍처**: 런타임, 에이전트, 워크스페이스, 트래커, 알림 모두 교체 가능. AHOY는 하드코딩된 컴포넌트
2. **이슈별 완전 격리**: git worktree로 각 이슈가 독립 브랜치에서 작업. AHOY는 단일 작업 공간
3. **CI 피드백 루프**: CI 실패를 자동으로 에이전트에게 라우팅하여 자율 수정. AHOY에 CI 연동 없음
4. **대규모 병렬 실행**: 수십 개 이슈 동시 처리. AHOY는 스프린트 단위 순차 처리
5. **통합 대시보드**: 웹 UI로 모든 에이전트 상태 실시간 모니터링
6. **리뷰 코멘트 자동 라우팅**: GitHub 리뷰를 에이전트에게 직접 전달

### AHOY가 더 나은 점
1. **Generator-Evaluator 분리**: Agent Orchestrator는 같은 에이전트가 생성+자체 테스트. 외부 평가자 개념 없음
2. **다중 모델 컨센서스**: 독립 평가자 합의 메커니즘 없음. CI 통과만으로 품질 판단
3. **Hook 기반 하드 차단**: 에이전트 행동 제한이 소프트한 설정 기반. 우회 가능
4. **파일 소유권 분리**: worktree 격리는 이슈간 격리이지 파일 소유권 분리가 아님
5. **Generator 의견 strip**: 없음
6. **계약 기반 개발**: contract.md 같은 공통 참조 없음
7. **컨텍스트 리셋**: handoff 문서 인계 전략 없음
8. **rework 제한**: CI 재시도 2회 제한은 있지만 코드 품질 평가 기반이 아님

### 배울 만한 구체적 아이디어
1. **플러그인 아키텍처 패턴**: eval_dispatch.py의 평가 모델을 플러그인 방식으로 교체 가능하게 설계 → 새 모델 추가 시 코드 수정 최소화
2. **이슈별 git worktree 격리**: 복수 스프린트 병렬 실행 시 파일 충돌 방지
3. **CI 피드백 자동 라우팅**: 생성된 코드의 CI 결과를 eval_dispatch.py에 자동 입력으로 전달

---

## AHOY 개선 제안 Top 3

### 1. 평가 모델 플러그인 시스템
**현재 문제**: eval_dispatch.py에 평가 모델이 하드코딩되어 새 모델 추가가 번거로움
**구현 방향**:
- `evaluators/` 디렉토리 신규 생성
- `evaluators/base.py`: 평가자 인터페이스 정의 (evaluate, parse_result, get_confidence)
- `evaluators/codex_evaluator.py`, `evaluators/gemini_evaluator.py` 등 구현
- `config.json`의 `evaluators` 배열로 활성 평가자 설정
- eval_dispatch.py는 플러그인 로더로 역할 전환

### 2. CI 피드백 루프 통합
**현재 문제**: 코드 레벨 평가 후 실제 CI 결과와의 연동 없음
**구현 방향**:
- `ci_monitor.py` 신규 생성: GitHub Actions/CI 상태 폴링
- passed 상태 이후 CI 결과를 추가 검증 단계로 포함
- CI 실패 시 자동으로 rework 트리거 (실패 로그를 Generator에게 전달)
- `sprint_state.json`에 `ci_status` 필드 추가

### 3. 스프린트 병렬 실행 지원 (git worktree)
**현재 문제**: 스프린트가 순차적으로만 실행 가능
**구현 방향**:
- `parallel_sprint.py` 신규 생성: 독립적 이슈들의 스프린트를 병렬 실행
- 각 스프린트를 별도 git worktree에서 실행하여 파일 충돌 방지
- 의존관계 그래프로 병렬 가능한 스프린트 자동 식별
- 통합 상태 뷰로 모든 병렬 스프린트 모니터링
