# CCManager (kbwo/ccmanager) 분석 리포트

> 분석일: 2026-03-28 (8차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | CCManager |
| GitHub URL | https://github.com/kbwo/ccmanager |
| 스타 | 965 |
| 최근 커밋 | 2026-03-27 (매우 활발) |
| 라이선스 | MIT |
| 언어 | TypeScript (Node.js) |
| 핵심 키워드 | 멀티 에이전트 세션 관리, Git Worktree, 8+ 에이전트 지원, 상태 감지 |

## 핵심 아키텍처

CCManager는 **멀티 AI 코딩 에이전트 세션 매니저**로, 단일 인터페이스에서 여러 에이전트(Claude Code, Gemini CLI, Codex CLI 등)를 Git Worktree 기반으로 병렬 관리한다.

### 핵심 구성요소

1. **세션 매니저**: tmux 없이 직접 세션 상태(Idle/Busy/Waiting) 감지 및 표시
2. **Worktree 매니저**: Git worktree 생성/병합/삭제를 통합 관리
3. **프로젝트 매니저**: 복수 레포지토리를 단일 인터페이스에서 관리
4. **Hook 시스템**: 상태 변경/worktree 생성 시 커스텀 명령 실행

### 지원 에이전트 (8종)

- Claude Code (teammate 모드 포함)
- Gemini CLI
- Codex CLI
- Cursor Agent
- Copilot CLI
- Cline CLI
- OpenCode
- Kimi CLI

### 상태 감지 시스템

에이전트별 맞춤 상태 감지 전략으로 Idle/Busy/Waiting 3상태를 실시간 추적. 상태 변경 시 Hook을 통해 외부 알림/자동화 트리거 가능.

### 설정 체계

- 전역 설정: `~/.config/ccmanager/config.json`
- 프로젝트 설정: `.ccmanager.json` (레포 루트)
- 계층적 병합: 프로젝트 설정이 전역 설정 오버라이드

## AHOY 비교 분석

### AHOY보다 나은 점

1. **8+ 에이전트 네이티브 지원**: AHOY는 Claude(Generator) + Codex/Gemini(Evaluator) 고정. CCManager는 8종 에이전트를 동적으로 워크트리별 배정 가능
2. **실시간 세션 상태 가시성**: 에이전트별 Idle/Busy/Waiting 상태를 TUI에서 실시간 표시. AHOY는 스프린트 상태만 추적
3. **세션 컨텍스트 전이**: 새 worktree 생성 시 Claude Code 세션 데이터(대화 히스토리, 컨텍스트) 자동 복사. AHOY의 handoff보다 세밀한 컨텍스트 보존
4. **Auto Approval (실험적)**: AI 검증을 통한 안전한 프롬프트 자동 승인. AHOY에는 없는 기능
5. **zero-dependency 아키텍처**: tmux 없이 독립 실행. 설치 장벽 최소화
6. **Devcontainer 통합**: 샌드박스 개발 환경과 네이티브 통합

### AHOY가 더 나은 점

1. **Generator-Evaluator 분리**: CCManager는 에이전트 간 역할 분리 없음. 모든 에이전트가 동등한 역할
2. **평가 메커니즘 부재**: CCManager는 세션 관리 도구이며 코드 품질 평가 기능 없음
3. **상태머신 강제**: CCManager는 상태 감지만 하고 전이 규칙을 강제하지 않음
4. **파일 소유권 분리**: CCManager는 파일 접근 제어 없음
5. **컨센서스 메커니즘**: 다중 에이전트가 있지만 합의 기반 의사결정 없음
6. **계약 기반 개발**: contract.md 같은 공유 참조점 없음

### 배울 만한 구체적 아이디어

1. **에이전트별 상태 감지 전략**: 평가 모델(Codex, Gemini)의 API 상태를 실시간 모니터링
   - 구현: eval_dispatch.py에 evaluator_status 추적 추가, Hook에서 평가자 health check
2. **상태 변경 Hook**: 스프린트 상태 변경 시 외부 알림(Slack, Discord) 자동 발송
   - 구현: .ahoy/hooks/on_state_change.sh 추가
3. **세션 데이터 자동 복사**: handoff 시 이전 세션의 관련 컨텍스트 자동 추출/복사
   - 구현: handoff 생성 시 Claude Code 세션 히스토리에서 관련 대화 자동 발췌
4. **계층적 설정 병합**: 전역 AHOY 설정 + 프로젝트별 오버라이드
   - 구현: `~/.ahoy/config.json` (전역) + `.ahoy/config.json` (프로젝트), 병합 로직
5. **에이전트 프리셋**: 자주 사용하는 에이전트 조합을 프리셋으로 저장
   - 구현: .ahoy/presets/ 디렉토리에 평가 모델 조합 프리셋

## AHOY 개선 제안 Top 3

### 1. 계층적 설정 시스템 (Global + Project Config)
- **현재**: 프로젝트별 .ahoy/ 설정만 존재
- **개선**: `~/.ahoy/global_config.json` (전역 기본값) + `.ahoy/config.json` (프로젝트 오버라이드) 계층 도입. 평가 모델 기본 선택, rework 최대 횟수, Hook 프로파일 등을 전역으로 관리
- **파일**: 신규 `~/.ahoy/global_config.json`, eval_dispatch.py 설정 로더 수정
- **효과**: 다중 프로젝트에서 AHOY 사용 시 반복 설정 제거

### 2. 평가자 상태 실시간 모니터링
- **현재**: 평가 요청 후 응답 대기만 함
- **개선**: Codex/Gemini API 상태(가용/과부하/다운)를 사전 체크, 비가용 시 대체 모델 자동 전환 + 사용자 알림
- **파일**: `eval_dispatch.py`에 `check_evaluator_health()` 함수 추가, `.ahoy/evaluator_status.json` 상태 캐시
- **효과**: 평가 실패로 인한 스프린트 중단 방지, 모델 폴백 자동화

### 3. 외부 알림 Hook 시스템
- **현재**: 상태 전이가 내부적으로만 처리
- **개선**: `.ahoy/hooks/on_state_change.sh` 스크립트를 상태 전이 시 자동 실행. passed/failed/rework 이벤트별 Slack/Discord/이메일 알림
- **파일**: `.ahoy/hooks/` 디렉토리, Hook 실행 로직 (eval_dispatch.py 또는 별도 hook_runner.py)
- **효과**: 팀 협업 시 스프린트 진행 상황 실시간 공유
