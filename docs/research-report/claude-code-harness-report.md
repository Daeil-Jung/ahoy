# Claude Code Harness (Chachamaru127) 분석 리포트

> 분석일: 2026-03-28

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **프로젝트명** | Claude Code Harness |
| **GitHub URL** | https://github.com/Chachamaru127/claude-code-harness |
| **스타** | ~332 |
| **최근 활동** | 활발 (Claude Code v2.1+ 호환 유지) |
| **언어** | TypeScript (core), Markdown (skills) |
| **특징** | Claude Code 전용 개발 하네스, Plan→Work→Review 사이클 |

## 핵심 아키텍처

### 5-Verb 워크플로우

AHOY의 상태머신과 직접 비교 가능한 구조화된 워크플로우:

1. **Setup** (`/harness-setup`) — 프로젝트 초기화, 규칙·명령 표면 설정
2. **Plan** (`/harness-plan`) — 아이디어 → `Plans.md` 변환 (수용 기준 포함)
3. **Work** (`/harness-work`) — 병렬 구현, 자동 탐지 또는 설정 가능한 워커 수
4. **Review** (`/harness-review`) — 4관점 코드 분석
5. **Release** (`/harness-release`) — CHANGELOG, 태그, GitHub 릴리스 생성

`/harness-work all` 하나로 plan 승인 후 전체 루프 실행 가능.

### TypeScript 가드레일 엔진

`core/src/`에 **13개 선언적 규칙(R01-R13)**을 TypeScript로 컴파일:

| 규칙 | 유형 | 설명 |
|------|------|------|
| R01 | Block | `sudo` 명령 차단 |
| R02 | Block | `.git/`, `.env`, 시크릿 쓰기 금지 |
| R03 | Block | 보호 파일 셸 쓰기 금지 |
| R04 | Ask | 프로젝트 외부 쓰기 시 확인 |
| R05 | Ask | `rm -rf` 확인 요구 |
| R06 | Block | `git push --force` 차단 |
| R10 | Block | `--no-verify` 금지 |
| R11 | Block | `git reset --hard main/master` 차단 |
| R12 | Warn | 보호 브랜치 직접 푸시 경고 |
| R13 | Warn | 보호 파일 편집 알림 |

### 4관점 리뷰 시스템

`/harness-review`는 코드를 4개 관점에서 분석:

1. **Security** — 취약점, 인젝션, 인증 갭
2. **Performance** — 병목, 메모리, 확장성
3. **Quality** — 패턴, 네이밍, 유지보수성
4. **Accessibility** — WCAG, 스크린 리더

### Agent Trace 시스템

모든 AI 편집을 `.claude/state/agent-trace.jsonl`에 자동 기록:
- 프로젝트명, 현재 태스크, 최근 수정 사항
- `/sync-status`로 Plans.md vs 실제 변경 감사(audit) 가능
- 기본 활성화, 설정 불필요

### 병렬 워커

```
/harness-work                # 자동 탐지
/harness-work --parallel 5   # 5개 워커 동시 실행
```

8+ 태스크는 자동 배치 분할, 배치 간 부분 리뷰 + 다음 배치 실행.

## AHOY와 비교 분석

### AHOY보다 나은 점

1. **TypeScript 컴파일 가드레일** — 규칙이 TypeScript로 컴파일되어 런타임 오버헤드 최소. AHOY의 Python Hook은 매 호출 시 인터프리팅
2. **4관점 체계적 리뷰** — Security/Performance/Quality/Accessibility 구분. AHOY는 평가 관점을 명시적으로 구분하지 않음
3. **Agent Trace (편집 감사 추적)** — 모든 AI 편집을 JSONL로 기록, 사후 감사 가능. AHOY에는 편집 이력 추적 메커니즘 없음
4. **병렬 워커 + 자동 배치** — 독립 태스크를 병렬 처리하며, 8+ 태스크 시 자동 배치 분할. AHOY는 순차 단일 스프린트
5. **Plans.md SSOT + sync-status** — 계획과 실제 구현의 동기화 상태를 명시적으로 추적/감사
6. **Evidence Pack** — 실행 결과의 재현 가능성을 문서화. 벤치마크 루브릭으로 정적/동적 증거 구분

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리** — claude-code-harness는 같은 Claude 모델이 생성과 리뷰를 모두 수행. 자기평가 편향 미차단
2. **다중 모델 컨센서스** — 리뷰가 단일 Claude 세션 내에서만 이루어짐. 외부 모델 교차 평가 없음
3. **파일 소유권 분리** — issues.json 같은 평가 결과 파일의 쓰기 권한 분리 없음. Claude가 모든 파일에 접근 가능
4. **Generator 의견 strip** — 리뷰어가 생성자와 같은 모델이므로 의견 분리 자체가 불가능
5. **rework 제한** — 최대 재작업 횟수 하드 리밋 없음. 무한 루프 가능성
6. **컨텍스트 리셋 메커니즘** — 3스프린트 handoff 같은 체계적 컨텍스트 관리 부재

### 배울 만한 구체적 아이디어

1. **Agent Trace JSONL 로깅**
   - 모든 파일 수정을 타임스탬프와 함께 기록
   - **적용**: AHOY에 `.ahoy/trace/` 디렉토리 추가, Hook에서 PostToolUse 시점에 편집 내용 JSONL 기록. handoff 문서 생성 시 trace 요약 자동 포함

2. **4관점 구조화 리뷰 프레임워크**
   - 보안/성능/품질/접근성 관점을 명시적으로 분리
   - **적용**: eval_dispatch.py의 평가 프롬프트를 관점별로 분리하여 4회 평가 → 관점별 이슈 집계. 또는 각 평가 모델에 다른 관점 할당

3. **Plans.md ↔ 코드 동기화 감사**
   - 계획 대비 실제 구현 드리프트를 정량화
   - **적용**: contract.md의 요구사항 항목 vs 실제 변경 파일을 자동 매핑, 미구현 항목 탐지 → rework 지시에 포함

4. **Evidence Pack (재현 가능한 검증)**
   - 평가 결과의 재현 가능성을 보장하는 문서화
   - **적용**: passed 상태 전이 시 평가 입출력 스냅샷을 `.ahoy/evidence/sprint-{n}/`에 자동 저장

---

## AHOY 개선 제안 Top 3

### 1. Agent Trace 시스템 도입

**문제**: Generator의 파일 수정 이력이 체계적으로 추적되지 않아 rework 시 무엇이 변경되었는지 파악 어려움

**제안**: 모든 파일 수정을 JSONL 형태로 자동 기록

**구현 방향**:
- `.ahoy/trace/sprint-{n}.jsonl` 파일 생성
- PostToolUse Hook에서 Write/Edit 작업 감지 시 자동 기록:
  ```json
  {"timestamp": "...", "tool": "Write", "file": "src/main.py", "lines_changed": 15, "sprint": 3, "state": "generated"}
  ```
- handoff 문서 생성 시 trace 요약 자동 포함
- eval_dispatch.py가 trace를 읽어 변경 범위 기반 평가 범위 최적화

### 2. 구조화된 다관점 평가 프레임워크

**문제**: 평가 모델이 단일 프롬프트로 모든 측면을 동시 평가하여 특정 관점이 누락될 수 있음

**제안**: 보안/정확성/성능/코드품질 4관점 평가를 명시적으로 분리

**구현 방향**:
- eval_dispatch.py에 `EVALUATION_PERSPECTIVES` 설정 추가:
  ```python
  PERSPECTIVES = ["security", "correctness", "performance", "code_quality"]
  ```
- 각 평가 모델에 관점을 배정하는 두 가지 전략:
  - **전략 A**: 각 모델이 4관점 모두 평가 → 관점별 컨센서스
  - **전략 B**: Codex에 security+correctness, Gemini에 performance+code_quality 할당 → 전문화
- issues.json에 `perspective` 필드 추가로 이슈 분류

### 3. Contract ↔ Code 동기화 감사

> **v0.2.0 구현 완료** — `validate_harness.py:audit_final_scope()` contract scope vs git diff 대조 + `eval_dispatch.py:parse_acceptance_criteria()` AC별 검증

**문제**: contract.md의 요구사항과 실제 생성 코드 간 드리프트를 체계적으로 탐지하지 못함

**제안**: contract.md의 수용 기준 vs 실제 변경 파일을 자동 매핑하여 누락 항목 탐지

**구현 방향**:
- contract.md에 요구사항별 ID 부여: `[REQ-001] 사용자 인증 API 구현`
- eval_dispatch.py에 contract 파싱 → 요구사항 추출 로직 추가
- 각 REQ에 대해 관련 파일 변경 존재 여부 확인
- 미충족 REQ를 issues.json에 `type: "contract_violation"` 으로 기록
- Generator에게 "REQ-003 미구현" 형태로 구체적 피드백 전달
