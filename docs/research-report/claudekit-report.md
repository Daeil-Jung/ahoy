# Claudekit 분석 리포트

> 분석일: 2026-03-28 (3차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Claudekit |
| GitHub URL | https://github.com/carlrannaberg/claudekit |
| 스타 | 637 |
| 포크 | 103 |
| 커밋 | 713 |
| 라이선스 | 미확인 |
| 언어 | TypeScript/JavaScript |
| 요구사항 | Node.js 20+, Claude Code Max plan |

## 핵심 아키텍처

### 모듈 구조

```
claudekit (CLI) ─┬─ Commands (slash commands)
                 ├─ Hooks (PreToolUse / PostToolUse / UserPromptSubmit)
                 ├─ Subagents (20+ 전문 에이전트)
                 └─ Utilities (git checkpoint, codebase map)
```

### 6-에이전트 병렬 코드 리뷰

`/code-review` 명령이 6개 전문 관점에서 동시에 코드를 분석:

| 관점 | 분석 내용 |
|------|-----------|
| Architecture | 구조, 패턴, 의존성 |
| Security | 취약점, 인증, 데이터 노출 |
| Performance | 병목, 메모리, 최적화 |
| Testing | 커버리지, 엣지 케이스, 모킹 |
| Quality | 코드 스타일, 가독성, 유지보수성 |
| Documentation | 주석, JSDoc, README |

### Spec 워크플로우 (6단계)

```
Implementation → Test Writing → Code Review → Iterative Improvement → Commit → Progress Tracking
```

각 단계에 Quality Gate 존재, 동적 에이전트 선택

### Hook 시스템 (실시간 보호)

**PreToolUse:**
- `file-guard`: .env, 키, 자격증명 파일 접근 차단

**PostToolUse:**
- 타입 체크, 린팅, 테스트 검증 자동 실행
- `check-any-changed`: TypeScript `any` 타입 사용 금지
- `check-comment-replacement`: 코드→주석 대체 감지

**UserPromptSubmit:**
- `codebase-map`: 프로젝트 구조 자동 컨텍스트 주입
- `thinking-level`: Claude 추론 능력 강화

### 20+ 전문 서브에이전트

도메인별 전문가 에이전트:
- **빌드**: webpack-expert, vite-expert
- **TypeScript**: typescript-expert, typescript-build-expert, typescript-type-expert
- **React**: react-expert, react-performance-expert
- **테스트**: testing-expert, jest-testing-expert, vitest-testing-expert, playwright-expert
- **인프라**: docker-expert, github-actions-expert, devops-expert
- **DB**: database-expert, postgres-expert, mongodb-expert
- **유틸**: code-search, triage-expert, code-review-expert, oracle

### 강제 위임 모델

> "ALL tasks and issues MUST be handled by specialized subagents. Do not attempt to solve problems directly."

1. `triage-expert`로 먼저 진단
2. 도메인 전문가에게 즉시 위임
3. 복잡한 디버깅은 triage를 통해 전문가 식별

### Git 체크포인트 시스템

- 자동 저장 + 원커맨드 복원
- 작업 전 자동 체크포인트 생성
- 실패 시 즉시 롤백 가능

## AHOY 대비 비교

### Claudekit이 AHOY보다 나은 점

1. **풍부한 도메인 전문가 에이전트**: 20+ 전문 서브에이전트가 도메인별 최적 분석 제공. AHOY는 범용 Generator 하나
2. **Git 체크포인트 시스템**: 자동 저장/복원으로 rework 시 안전한 롤백. AHOY는 상태머신만 관리하고 코드 롤백은 수동
3. **Codebase Map 자동 주입**: UserPromptSubmit hook으로 프로젝트 구조를 자동으로 Generator 컨텍스트에 포함
4. **코드→주석 대체 감지**: PostToolUse hook이 실제 코드를 주석으로 대체하는 패턴을 자동 감지. 코드 품질 저하 방지
5. **Hook 성능 프로파일링**: 느린 hook 자동 식별 CLI. AHOY hook에도 유용
6. **세션 기반 Hook 제어**: 설정 변경 없이 임시로 hook 비활성화 가능

### AHOY가 Claudekit보다 나은 점

1. **Generator-Evaluator 구조적 분리**: Claudekit의 모든 에이전트는 같은 Claude 모델. 자기평가 편향 존재. AHOY는 외부 모델로 평가
2. **다중 모델 컨센서스**: Claudekit은 단일 모델 기반. AHOY는 최소 2개 외부 모델 합의 필수
3. **파일 소유권 분리**: Claudekit은 모든 에이전트가 모든 파일에 접근. AHOY는 issues.json 쓰기 권한 물리적 분리
4. **Generator 의견 strip**: Claudekit에는 에이전트 출력에서 주관적 판단을 제거하는 메커니즘 없음
5. **스프린트 상태머신**: Claudekit의 Spec 워크플로우는 단계가 있으나 하드 차단 없음. 에이전트가 단계를 건너뛸 수 있음
6. **계약 기반 개발**: contract.md 같은 Generator-Evaluator 공통 참조점 없음. 에이전트별 독립 판단

### 배울 만한 구체적 아이디어

1. **코드→주석 대체 감지 Hook**
   - PostToolUse hook에 `check-comment-replacement` 로직 이식
   - Generator가 구현 대신 `// TODO` 주석으로 대체하는 패턴 자동 감지
   - `hooks/post_tool_use/` 에 새 훅 스크립트 추가

2. **Codebase Map 기반 컨텍스트 프리로드**
   - `UserPromptSubmit` 시점에 프로젝트 구조 자동 스캔
   - contract.md에 관련 파일 트리 자동 첨부
   - 기존 제안 "Generator 컨텍스트 자동 패킹"의 구체적 구현 방식

3. **Git 체크포인트 자동화**
   - `generated` 상태 진입 시 자동 git checkpoint 생성
   - rework 시 checkpoint로 롤백 후 재생성
   - `hooks/pre_tool_use/` 에 자동 체크포인트 훅 추가

4. **Triage-Expert 패턴 → 이슈 복잡도 사전 분류**
   - 스프린트 시작 시 이슈 복잡도를 자동 분류
   - 복잡도에 따라 평가 강도/모델 자동 결정
   - 기존 제안 "태스크 복잡도 기반 평가 강도 자동 조절"의 구체적 참조

---

## AHOY 개선 제안 Top 3

### 1. 코드→주석 대체 감지 Hook

> **v0.2.0 구현 완료** — `validate_harness.py:check_post_edit_quality()` TODO/FIXME/stub/placeholder 패턴 자동 탐지

- **구현 대상**: `hooks/post_tool_use/` (새 훅 스크립트)
- **변경 내용**: Generator의 파일 수정에서 실제 코드 라인이 `// TODO`, `# placeholder`, `pass` 등으로 대체된 비율을 계산. 임계값(예: 10%) 초과 시 warning 또는 rework 강제
- **효과**: Generator의 "구현 회피" 패턴 자동 감지
- **참조**: Claudekit `check-comment-replacement`

### 2. Git 체크포인트 기반 안전한 Rework
- **구현 대상**: Hook 시스템 (상태 전이 시점에 git tag/stash 자동 생성)
- **변경 내용**: `generated` 상태 진입 시 `git tag ahoy-sprint-{n}-gen-{attempt}` 자동 생성. rework 시 이전 태그로 롤백 옵션 제공
- **효과**: rework 시 이전 시도의 코드를 보존하면서 안전하게 재시도
- **참조**: Claudekit Git Checkpoint System

### 3. Triage 기반 이슈 복잡도 자동 분류
- **구현 대상**: `eval_dispatch.py` (planned→contracted 전이 시점)
- **변경 내용**: contract.md의 요구사항 수, 변경 대상 파일 수, 의존성 깊이를 분석하여 low/medium/high 복잡도 자동 분류. 복잡도별 평가 강도(모델 수, 평가 라운드) 자동 결정
- **효과**: 단순 이슈에 과도한 평가 비용 방지, 복잡한 이슈에 충분한 검증 보장
- **참조**: Claudekit triage-expert, Oh-My-Codex 스마트 에스컬레이션
