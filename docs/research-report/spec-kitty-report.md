# Spec-Kitty 분석 리포트

> 분석일: 2026-03-28 (6차)

## 프로젝트 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Spec-Kitty |
| URL | https://github.com/Priivacy-ai/spec-kitty |
| 스타 | ~300+ (추정) |
| 최근 활동 | 매우 활발 (v2.1.x 안정 릴리스, 2026-03) |
| 라이선스 | 오픈소스 |
| PyPI | spec-kitty-cli |

## 핵심 아키텍처

### Spec-Driven Development 워크플로우

Spec-Kitty는 "제품 의도 → 구현"까지의 반복 가능한 경로를 제공하는 CLI 워크플로우 도구:

```
spec → plan → tasks → implement → review → merge
```

### 라이프사이클 레인 (Lifecycle Lanes)

7개의 정규 레인으로 작업 상태 관리:
1. **planned**: 작업 정의됨
2. **claimed**: 에이전트/개발자가 작업 요청
3. **in_progress** (UI에서 `doing`): 구현 진행 중
4. **for_review**: 리뷰 대기
5. **done**: 완료
6. **blocked**: 차단됨
7. **canceled**: 취소

### Git Worktree 기반 병렬 실행

- 각 작업 패키지가 `.worktrees/` 아래 격리된 git worktree에서 실행
- 여러 에이전트가 동시에 다른 작업 패키지를 병렬 처리
- worktree 간 충돌 없이 독립적 개발

### 칸반 대시보드

- 실시간 레인 전이 스트림
- 프로덕트 오너, 리뷰어, AI 어시스턴트를 위한 단일 진실 소스
- 피처별 진행 상태 시각화

### 멀티 에이전트 지원

Claude Code, GitHub Copilot, Gemini CLI, Cursor, Windsurf 등 7+ AI 코딩 에이전트와 호환.

### 오케스트레이터 API

- `spec-kitty orchestrator-api`로 CLI 오케스트레이션 노출
- 멀티 에이전트 피처 개발 조율 (3-5 에이전트 동시)
- 병렬 구현 추적 + 대시보드 메트릭

## AHOY와의 비교

### AHOY보다 나은 점

1. **7단계 라이프사이클 레인**: AHOY의 4단계(planned→contracted→generated→passed)보다 세분화. `claimed`, `for_review`, `blocked`, `canceled` 추가로 실제 개발 프로세스에 가까움
2. **Git Worktree 병렬 실행**: 여러 스프린트/이슈를 동시에 병렬 처리. AHOY는 직렬 실행만 지원
3. **칸반 대시보드**: 실시간 시각적 진행 상태. AHOY는 터미널 텍스트 출력만
4. **멀티 에이전트 호환**: 7+ AI 코딩 에이전트 지원. AHOY는 Claude Code 전용
5. **오케스트레이터 API**: 외부 도구/서비스와 프로그래밍적 통합. AHOY는 API 없음
6. **자동 머지**: review 후 자동 머지 워크플로우. AHOY는 수동

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리**: Spec-Kitty는 리뷰가 있지만 동일 에이전트/모델이 수행 가능. AHOY의 외부 모델 평가가 편향에 강함
2. **다중 모델 필수 컨센서스**: Spec-Kitty는 컨센서스 개념 없음. AHOY의 2+ 외부 모델 합의가 더 견고
3. **Hook 기반 하드 차단**: Spec-Kitty의 레인 전이는 소프트 (에이전트 자율). AHOY의 PreToolUse/PostToolUse Hook은 우회 불가
4. **파일 소유권 분리**: Spec-Kitty에 없음
5. **Generator 의견 strip**: Spec-Kitty에 없음
6. **계약 기반 평가**: Spec-Kitty의 spec은 가이드. AHOY의 contract.md는 평가의 법적 기준

## 배울 만한 구체적 아이디어

### 1. 세분화된 라이프사이클 레인
- **현재 AHOY**: 4단계 상태머신
- **제안**: `blocked`, `for_review` 레인 추가. `generated` → `for_review` → `passed` 또는 `generated` → `blocked` (외부 의존성)
- **구현**: 상태머신에 2개 상태 추가, Hook에서 blocked 조건 자동 감지

### 2. Git Worktree 병렬 스프린트
- **현재 AHOY**: 직렬 스프린트 실행
- **제안**: 독립적인 이슈를 git worktree로 병렬 처리. 의존성 없는 스프린트 동시 실행
- **구현**: `sprint_parallel.py` — worktree 생성/관리, 병렬 eval_dispatch 호출

### 3. 스프린트 대시보드
- **현재 AHOY**: 텍스트 로그
- **제안**: 터미널 기반 칸반 대시보드. 현재 스프린트 상태, rework 횟수, 평가 히스토리 실시간 표시
- **구현**: Python `textual` 라이브러리로 TUI 대시보드 (`ahoy_dashboard.py`)

## AHOY 개선 제안 Top 3

### 1. `blocked` / `for_review` 상태 추가 (확장 상태머신)
- **파일**: Hook 설정 파일, 상태 전이 규칙 수정
- **구현**: `generated` 이후 자동 평가 전 `for_review` 상태 삽입 (사람 리뷰 옵트인). 외부 API 대기/환경 문제 시 `blocked` 상태로 전이. blocked 원인 자동 기록 + 해소 시 자동 복귀
- **효과**: 실제 개발 프로세스에 가까운 상태 관리, 외부 의존성으로 인한 스프린트 교착 방지

### 2. Git Worktree 병렬 스프린트 실행
- **파일**: `sprint_parallel.py` (신규), `eval_dispatch.py` 멀티인스턴스 지원
- **구현**: 의존성 분석 → 독립 이슈 식별 → 각 이슈별 git worktree 생성 → 병렬 Generator 실행 → 병렬 평가 → 결과 병합. worktree 간 충돌 시 sequential 폴백
- **효과**: 독립 이슈 처리 시간 N배 단축 (N = 병렬 수)

### 3. 오케스트레이터 API 노출
- **파일**: `ahoy_api.py` (신규), FastAPI 기반
- **구현**: `/sprint/status`, `/sprint/start`, `/sprint/rework`, `/sprint/history` 엔드포인트. 외부 CI/CD, 대시보드, Slack 봇에서 AHOY 상태 조회/제어 가능
- **효과**: AHOY를 독립 서비스로 운용 가능, 외부 도구와 통합
