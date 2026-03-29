# Overstory 분석 리포트

> 분석일: 2026-03-28

## 프로젝트 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Overstory |
| URL | https://github.com/jayminwest/overstory |
| 스타 | 1.1k |
| 총 커밋 | 1,278 |
| 라이선스 | MIT |
| 주요 언어 | TypeScript (Commander.js 기반 CLI) |
| 생태계 | os-eco (Sapling, Mulch, Seeds, Canopy, Overstory) |

## 핵심 아키텍처

Overstory는 단일 코딩 세션을 **다중 에이전트 팀**으로 변환하는 오케스트레이션 프레임워크. git worktree + tmux 기반 격리, SQLite 메일 시스템으로 조율.

### 에이전트 계층 구조

```
Orchestrator (multi-repo coordinator, depth 0)
├─ Coordinator (persistent project orchestrator)
│  ├─ Supervisor/Lead (team lead, depth 1)
│  └─ Workers (depth 2, leaf nodes)
│     ├─ Scout (read-only 탐색)
│     ├─ Builder (read-write 구현)
│     ├─ Reviewer (read-only 검증)
│     └─ Merger (branch 전문가)
└─ Monitor (Tier 2 연속 순찰)
```

- **Depth limit**: 기본 2, 설정 가능. 런어웨이 스포닝 방지
- **9개 기본 에이전트 정의**: 역할별 능력/제한 명시

### SQLite 메일 시스템 (핵심 차별점)

- **저장소**: `.overstory/mail.db` (bun:sqlite)
- **모드**: WAL (Write-Ahead Logging) — 다중 에이전트 동시 접근
- **지연시간**: ~1-5ms per query
- **메시지 타입**: 8종 typed protocol
  - `worker_done`, `merge_ready`, `merged`, `escalation`
  - `health_check`, `dispatch`, `assign`, `broadcast`
- **그룹 주소**: `@all`, `@builders` 등 브로드캐스트
- **감사 추적**: 모든 상태 변경이 메시지로 기록, 추적 가능

### Tool-Call Guards (가드레일)

`guard-rules.ts`에 공유 가드 상수 중앙 관리:

| 런타임 | 가드 메커니즘 | 안정도 |
|--------|-------------|--------|
| Claude Code | settings.local.json hooks | Stable |
| Sapling | .sapling/guards.json | Stable |
| Pi | Extension 기반 | Experimental |
| Gemini | --sandbox flag | Experimental |
| Goose | Profile permissions | Experimental |
| Codex | OS sandbox | Experimental |

- **능력별 tool list**: builder/scout/reviewer 각각 허용 도구 목록 분리
- **Bash 패턴 제한**: 위험 명령 실행 차단
- **파일 소유권**: `--files f1,f2,...` 플래그로 에이전트별 배타적 파일 스코프

### Instruction Overlays (동적 CLAUDE.md)

2계층 시스템:
1. **Base layer**: `.md` 파일로 정의된 워크플로우 (모든 스포닝 에이전트에 자동 주입)
2. **Per-task overlay**: 태스크별 스코프/제약 동적 생성

### Watchdog 시스템 (3-Tier)

| Tier | 컴포넌트 | 역할 |
|------|----------|------|
| 0 | Mechanical daemon (`daemon.ts`) | tmux/pid 생존 확인 |
| 1 | AI-assisted triage (`triage.ts`) | 실패 진단/분류 |
| 2 | Monitor agent | 연속 fleet 순찰 |

실패 에이전트 → 에스컬레이션 메시지 발행 (침묵 계속 방지)

### Merge Conflict Resolution

- FIFO 머지 큐
- 4-Tier 충돌 해결 전략
- Merger 전문 에이전트가 브랜치 통합 담당

### 관찰성 (Observability)

- **37+ CLI 명령**: coordination, messaging, task groups, merging, observability
- **대시보드**: `ov dashboard`
- **토큰 계측**: JSONL 트랜스크립트에서 세션 메트릭 추출, 비용 분석
- **게이트웨이**: z.ai, OpenRouter, self-hosted API 라우팅

## AHOY와의 비교 분석

### AHOY보다 나은 점

| 영역 | Overstory 장점 | 상세 |
|------|---------------|------|
| **다중 에이전트 병렬 실행** | git worktree 기반 격리된 병렬 에이전트 | AHOY는 순차 스프린트. Overstory는 여러 이슈를 동시 처리 가능 |
| **에이전트간 통신 프로토콜** | SQLite 메일 시스템 (typed, auditable) | AHOY는 에이전트간 통신 메커니즘 없음 (Generator-Evaluator만) |
| **역할 기반 에이전트 분리** | Scout/Builder/Reviewer/Merger 능력 분리 | AHOY의 Generator는 단일 역할. 탐색/구현/검증 구분 없음 |
| **11개 런타임 어댑터** | Claude, Codex, Gemini, Aider 등 지원 | AHOY는 Claude Code 전용 |
| **파일 스코프 강제** | `--files` 플래그로 에이전트별 배타적 파일 소유 | AHOY의 파일 소유권은 issues.json에만 적용, 코드 파일은 미적용 |
| **Watchdog 3-Tier** | 기계적 + AI + 순찰 에이전트 3중 감시 | AHOY는 rework 카운터만으로 실패 관리 |
| **Observability** | 37+ CLI, 대시보드, 토큰 비용 추적 | AHOY는 관찰성 도구 미비 |

### AHOY가 더 나은 점

| 영역 | AHOY 장점 | 상세 |
|------|-----------|------|
| **Generator-Evaluator 완전 분리** | 외부 모델이 평가 | Overstory의 Reviewer는 같은 런타임 내 에이전트. 진정한 외부 모델 평가 아님 |
| **다중 모델 컨센서스** | Codex+Gemini 합의 필수 | Overstory는 단일 런타임 내 리뷰. 크로스 모델 합의 없음 |
| **Generator 의견 제거** | 주관적 판단 strip | Overstory는 에이전트 출력 필터링 없음 |
| **상태머신 하드 차단** | Hook으로 상태 전이 강제 | Overstory는 메시지 기반 조율이지만, 상태 전이 규칙이 소프트 |
| **계약 기반 개발** | contract.md가 공통 참조점 | Overstory의 spec은 있지만, Generator/Evaluator 간 계약 형태가 아님 |
| **컨텍스트 리셋** | 3 스프린트마다 handoff | Overstory는 checkpoint 시스템이 있지만, 주기적 강제 리셋은 아님 |

## 배울 만한 구체적 아이디어

### 1. SQLite 기반 평가 감사 로그
```python
# eval_dispatch.py에 eval_audit.db 추가
# 모든 평가 요청/응답을 SQLite WAL 모드로 기록
# 테이블: eval_requests, eval_responses, consensus_decisions
# 이점: 평가 히스토리 쿼리 가능, 패턴 분석, 디버깅
```

### 2. 에이전트별 파일 스코프 강제 확장
```python
# contract.md의 allowed_paths를 Hook에서 실제 강제
# PreToolUse Hook에서 Write/Edit 대상 파일이
# 해당 스프린트의 allowed_paths 내인지 검증
# 범위 외 수정 시도 → 하드 차단
```

### 3. Watchdog 패턴 (Tier 0 기계적 감시)
```python
# eval_dispatch.py 프로세스 health check
# - API 호출 타임아웃 감지
# - 평가 모델 응답 없음 감지
# - 자동 재시도 + 에스컬레이션 (다른 모델로 폴백)
```

### 4. Typed Protocol 메시지
```python
# Generator ↔ Evaluator 통신을 typed message로 표준화
# MessageType: EVAL_REQUEST, EVAL_RESPONSE, REWORK_ORDER, PASS_CONFIRMATION
# JSON Schema 검증으로 메시지 형식 강제
```

---

## AHOY 개선 제안 Top 3

### 1. SQLite 평가 감사 로그 시스템
- **출처**: Overstory의 SQLite 메일 시스템
- **구현 방향**: `eval_dispatch.py`에 `eval_audit.db` 추가. WAL 모드로 모든 평가 요청/응답/컨센서스 결정 기록. `ahoy audit` 명령으로 히스토리 쿼리. 평가자별 pass율 추적으로 아첨 감지 데이터 기반 구축
- **대상 파일**: `eval_dispatch.py` (SQLite 연동), 신규 `ahoy_audit.py` (CLI)

### 2. 코드 파일 수준 스코프 잠금 (File Scope Lock)
- **출처**: Overstory의 `--files` 배타적 파일 소유권
- **구현 방향**: contract.md에 `allowed_files` 명시. PreToolUse Hook에서 Write/Edit 대상 파일이 allowed_files 내인지 검증. 범위 외 수정 → 하드 차단 + rework 트리거. 현재 AHOY의 디렉토리 스코프 잠금 제안을 파일 레벨로 세분화
- **대상 파일**: PreToolUse Hook 스크립트, contract.md 스키마

### 3. 평가 프로세스 Watchdog (Health Monitor)
- **출처**: Overstory의 3-Tier Watchdog
- **구현 방향**: `eval_dispatch.py`에 Tier 0 기계적 감시 추가. API 호출 타임아웃(30초), 연속 실패 감지(3회), 모델 폴백 로직(Codex fail → Gemini only로 경고 평가). 장애 시 자동 에스컬레이션 대신 안전한 fail
- **대상 파일**: `eval_dispatch.py` (타임아웃/재시도 로직)
