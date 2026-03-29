# Oh-My-Codex (OMX) 분석 리포트

> 분석일: 2026-03-28

## 프로젝트 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Oh-My-Codex (OMX) |
| URL | https://github.com/Yeachan-Heo/oh-my-codex |
| 스타 | 2.7k |
| 최근 릴리즈 | v0.11.9 (2026-03-25) |
| 총 커밋 | 1,155 |
| 릴리즈 수 | 73 |
| 라이선스 | MIT |
| 주요 언어 | TypeScript (91.3%), Rust (4.8%) |

## 핵심 아키텍처

OMX는 OpenAI Codex CLI를 대체하지 않고 **워크플로우 레이어**로 감싸는 구조. Codex가 실행 엔진으로 유지되고, OMX가 프롬프트/스킬/상태 관리를 추가한다.

### 3계층 구조

1. **Prompts Layer**: `/prompts:architect`, `/prompts:executor` 등 역할 기반 재사용 프롬프트
2. **Skills Layer**: `$plan`, `$ralph`, `$team`, `$deep-interview`, `$autopilot` 워크플로우
3. **State Layer**: `.omx/` 디렉토리에 plans, logs, memory, runtime state 영속화

### 핵심 워크플로우

| 스킬 | 설명 |
|------|------|
| `$plan` | 분석 → 계획 수립 단계 |
| `$ralph` | 단일 에이전트 순차 실행 (persistent sequential) |
| `$team` | tmux/worktree 기반 다중 에이전트 병렬 실행 |
| `$deep-interview` | 1문1답 명확화 루프, 필요시 에스컬레이션 |
| `$autopilot` | 자동 모드 실행 |

### 추천 플로우

```
omx --madmax --high → /prompts:architect → $plan → $ralph/$team
```

에이전트가 태스크 규모에 따라 `$ralph`(순차) vs `$team`(병렬)을 **자동 판단하여 에스컬레이션**하는 구조.

### Team 모드 상세

- `omx team 3:executor` 형태로 워커 수 + 역할 지정
- tmux/psmux 백엔드로 durable 세션 관리
- status/resume/shutdown 명령으로 팀 라이프사이클 관리
- git worktree 기반 격리

## AHOY와의 비교 분석

### AHOY보다 나은 점

| 영역 | OMX 장점 | 상세 |
|------|----------|------|
| **스마트 에스컬레이션** | 에이전트가 자동으로 단일→팀 전환 판단 | AHOY는 수동으로 스프린트 스코프 결정. OMX는 태스크 복잡도 기반 자동 에스컬레이션 |
| **역할 기반 프롬프트 시스템** | `/prompts:architect`, `/prompts:executor` 등 분리 | AHOY는 단일 Generator 역할. 역할별 프롬프트 최적화 없음 |
| **인터뷰 루프** | `$deep-interview`로 명세 불확실성 사전 해소 | AHOY의 contract.md는 정적. 동적 명확화 프로세스 없음 |
| **Cross-platform 지원** | macOS/Linux(tmux) + Windows(psmux) | AHOY는 Linux/macOS만 |
| **Shell 인스펙션** | `omx sparkshell`로 런타임 상태 실시간 조회 | AHOY는 상태 조회가 issues.json 파일 직접 읽기에 의존 |
| **성숙도** | 73 릴리즈, 1155 커밋, 12개 언어 문서 | AHOY는 초기 단계 |

### AHOY가 더 나은 점

| 영역 | AHOY 장점 | 상세 |
|------|-----------|------|
| **Generator-Evaluator 분리** | 외부 모델이 평가 | OMX는 Codex 자체가 실행+리뷰. 자기평가 편향 구조적 미해결 |
| **다중 모델 컨센서스** | 2+ 모델 합의 필수 | OMX는 단일 모델(Codex) 기반. 크로스 모델 검증 없음 |
| **상태머신 기반 스프린트** | planned→contracted→generated→passed | OMX의 상태 관리는 .omx/ 파일 기반이지만, 명시적 상태 전이 규칙 강제 없음 |
| **Hook 기반 하드 차단** | PreToolUse/PostToolUse 강제 | OMX는 Hook 시스템 문서화 미흡, 우회 방지 메커니즘 불명확 |
| **파일 소유권 분리** | issues.json 쓰기 권한 물리적 분리 | OMX는 모든 상태 파일에 에이전트가 자유 접근 |
| **Generator 의견 제거** | 주관적 판단 자동 strip | OMX에 해당 메커니즘 없음 |

## 배울 만한 구체적 아이디어

### 1. 자동 에스컬레이션 패턴
```
# AHOY 적용 방향
# contract.md에 complexity_score 필드 추가
# eval_dispatch.py가 복잡도 기반으로 자동 병렬 평가 or 심층 평가 결정
complexity_threshold:
  simple: 1 evaluator
  moderate: 2 evaluators (current default)
  complex: 3 evaluators + forced disagreement
```

### 2. Deep Interview → Contract 생성 자동화
```
# planned → contracted 전이 시 명확화 루프 삽입
# Generator에게 contract.md 초안 제시 후 1문1답 명확화
# 불확실한 요구사항 자동 탐지 → 질문 생성 → 답변 반영
```

### 3. 런타임 상태 인스펙션 도구
```
# ahoy status 명령 추가
# 현재 스프린트 상태, rework 횟수, 평가 히스토리를
# 터미널에서 실시간 조회 가능하도록
```

---

## AHOY 개선 제안 Top 3

### 1. 태스크 복잡도 기반 평가 강도 자동 조절
- **출처**: OMX의 스마트 에스컬레이션
- **구현 방향**: `eval_dispatch.py`에 complexity estimator 추가. contract.md의 변경 파일 수, 코드 라인 수, 의존성 깊이로 복잡도 점수 산출. 점수별로 평가자 수/반복 횟수 자동 조절
- **대상 파일**: `eval_dispatch.py`, `contract.md` 스키마

### 2. Contract 명확화 인터뷰 루프 (planned → contracted 전이 강화)
- **출처**: OMX의 `$deep-interview`
- **구현 방향**: planned 상태에서 Generator에게 contract 초안을 보여주고, 모호한 요구사항을 자동 감지하여 1문1답 명확화. 결과를 contract.md에 반영 후 contracted 전이
- **대상 파일**: Hook 스크립트 (planned→contracted 전이), contract.md 템플릿

### 3. 실시간 스프린트 상태 조회 CLI
- **출처**: OMX의 `omx sparkshell` / `omx team status`
- **구현 방향**: `ahoy_status.py` CLI 도구 추가. issues.json + 스프린트 상태 + rework 카운트 + 최근 평가 결과를 포맷팅하여 터미널 출력. `--watch` 모드로 실시간 갱신
- **대상 파일**: 신규 `ahoy_status.py`, issues.json 읽기 전용 접근
