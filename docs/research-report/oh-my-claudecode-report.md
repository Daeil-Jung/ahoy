# Oh-My-Claudecode (OMC) 분석 리포트

> 분석일: 2026-03-27

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Oh-My-Claudecode (OMC) |
| URL | https://github.com/Yeachan-Heo/oh-my-claudecode |
| 스타 | 13.5k |
| 포크 | 883 |
| 최근 활동 | 활발 (main 브랜치 지속 업데이트) |

## 핵심 아키텍처

### 오케스트레이션 파이프라인
단계적 실행 모델: `team-plan → team-prd → team-exec → team-verify → team-fix (loop)`

### 실행 모드 (7가지)
1. **Team**: Claude 에이전트들이 공유 태스크 리스트에서 협업
2. **omc team CLI**: tmux 워커로 codex/gemini/claude 프로세스 스폰
3. **ccg**: `/ask codex` + `/ask gemini` 통한 삼중 모델 합성
4. **Autopilot**: 자율 단일 에이전트 실행
5. **Ralph**: 검증/수정 루프 지속 모드
6. **Ultrawork (ulw)**: 비팀 작업 최대 병렬처리
7. **Pipeline**: 순차 단계 처리

### 32개 전문 에이전트
아키텍처, 리서치, 디자인, 테스팅, 데이터 사이언스 등 도메인별 전문가 에이전트. 스마트 모델 라우팅으로 단순 태스크 → Haiku, 복잡한 추론 → Opus 자동 선택.

### 멀티 모델 조율
- CLI 기반 팀 런타임으로 온디맨드 워커 스폰
- Claude, Codex, Gemini 네이티브 지원
- Provider Advisor (`omc ask`)로 개별 모델 자문

## AHOY와 비교

### AHOY보다 나은 점
1. **Team Mode 실행**: 여러 에이전트가 공유 태스크 리스트에서 병렬 작업. AHOY는 단일 Generator 실행
2. **다양한 실행 모드**: 7가지 실행 패턴으로 태스크 특성에 맞춤 실행. AHOY는 스프린트 루프 단일 패턴
3. **비용 최적화**: Haiku/Opus 자동 선택으로 30-50% 토큰 절약. AHOY는 고정 모델 할당
4. **Rate Limit 자동 처리**: `omc wait`로 한도 리셋 시 자동 재개. AHOY에는 해당 기능 없음
5. **알림 통합**: Discord, Telegram, Slack, Webhook 콜백 지원
6. **team-verify 단계**: 실행 후 자동 검증 루프

### AHOY가 더 나은 점
1. **Generator-Evaluator 엄격 분리**: OMC의 team-verify는 같은 Claude 에이전트가 자기 작업을 검증할 수 있음. AHOY는 구조적으로 외부 모델만 평가
2. **다중 독립 평가자 컨센서스**: OMC의 ccg 모드가 유사하지만, AHOY처럼 "하나라도 fail → 최종 fail" 엄격 규칙은 없음
3. **상태머신 엄격성**: OMC 파이프라인이 유사하지만 Hook 기반 하드 차단 없음. 에이전트가 단계를 우회할 가능성 존재
4. **파일 소유권 강제**: OMC는 모든 에이전트가 모든 파일에 접근 가능
5. **주관적 판단 제거**: Generator 의견 strip 메커니즘 없음
6. **계약 기반 개발**: contract.md 같은 명시적 공통 참조 문서 없음

### 배울 만한 구체적 아이디어
1. **team-plan → team-prd → team-exec → team-verify → team-fix 파이프라인**: AHOY의 planned→contracted→generated→passed에 PRD(Product Requirements Document) 단계를 추가하면 contract.md 품질 향상 가능
2. **Rate Limit 관리**: eval_dispatch.py에 API 한도 감지 및 자동 대기/재개 로직 추가
3. **HUD Statusline**: 실시간 진행 상황 시각화 → AHOY 스프린트 진행 상태 대시보드로 적용

---

## AHOY 개선 제안 Top 3

### 1. PRD 단계 추가로 contract.md 품질 강화
**현재 문제**: contract.md가 바로 작성되어 요구사항 누락 가능성
**구현 방향**:
- 스프린트 상태머신에 `planned → prd → contracted → generated → passed` 로 prd 단계 삽입
- `hooks/pre_tool_use.py`에서 prd 문서 존재 여부 검증 후 contract 작성 허용
- PRD 템플릿 파일(`templates/prd_template.md`) 추가

### 2. Rate Limit 감지 및 자동 대기 메커니즘
**현재 문제**: 외부 API 호출 시 rate limit 발생하면 평가 실패로 처리됨
**구현 방향**:
- `eval_dispatch.py`에 HTTP 429 응답 감지 로직 추가
- `rate_limit_handler.py` 모듈 신규 생성: 대기 시간 계산 + 자동 재시도
- `sprint_state.json`에 `rate_limited_at` 타임스탬프 필드 추가로 상태 추적

### 3. 스프린트 진행 상태 실시간 대시보드
**현재 문제**: 스프린트 진행 상황을 파일 기반으로만 확인 가능
**구현 방향**:
- `dashboard.py` 신규 생성: sprint_state.json 실시간 파싱 + 터미널 UI 출력
- 현재 스프린트 단계, rework 횟수, 평가 결과 히스토리 시각화
- `--watch` 모드로 자동 갱신 지원
