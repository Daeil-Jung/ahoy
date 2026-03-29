# LangChain Open SWE 분석 리포트

> 분석일: 2026-03-28 (6차)

## 프로젝트 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Open SWE |
| URL | https://github.com/langchain-ai/open-swe |
| 스타 | ~8,400+ |
| 최근 활동 | 매우 활발 (2026-03 출시, GitHub 트렌딩 #2) |
| 라이선스 | MIT |
| 제작 | LangChain |

## 핵심 아키텍처

### 비동기 클라우드 코딩 에이전트

Open SWE는 Stripe(Minions), Ramp(Inspect), Coinbase(Cloudbot)이 독립적으로 구축한 사내 코딩 에이전트의 공통 아키텍처 패턴을 오픈소스화한 프로젝트다.

### 핵심 구성 요소

1. **LangGraph 기반 에이전트 루프**: 상태 기반 에이전트 실행. 도구 호출, LLM 추론, 상태 전이를 그래프로 관리
2. **Deep Agents**: 서브에이전트 오케스트레이션. 복잡한 태스크를 하위 에이전트에게 위임
3. **클라우드 샌드박스 (Daytona)**: 각 태스크가 격리된 Linux 환경에서 실행. 완전한 셸 접근 + 에러 격리
4. **미들웨어 시스템**: LLM 결정 루프 전후에 실행되는 결정론적 Hook

### 미들웨어 시스템 (핵심 차별점)

Open SWE의 미들웨어는 AHOY의 Hook과 직접 비교 가능한 핵심 아키텍처:

- **before_model 미들웨어**: LLM 호출 전 실행. `check_message_queue_before_model` — 실행 중 외부 메시지 주입
- **after_model 미들웨어**: LLM 호출 후 실행. `open_pr_if_needed` — LLM이 PR 생성을 잊어도 강제 생성
- **결정론적 보장**: LLM 행동에 의존하지 않는 안전망. 특정 행동이 반드시 발생하도록 강제
- **에러 핸들링**: 미들웨어 수준에서 에러 포착 및 복구

### 호출 방식

- **Slack**: 봇 멘션으로 태스크 할당
- **Linear**: 이슈 코멘트로 에이전트 호출
- **GitHub**: PR 코멘트로 에이전트 호출
- **CLI**: 직접 명령

### 관찰성 (Observability)

LangSmith 통합으로 에이전트 실행 추적, 컨텍스트 엔지니어링 디버그, 변경 효과 평가.

## AHOY와의 비교

### AHOY보다 나은 점

1. **미들웨어 결정론적 보장 패턴**: `open_pr_if_needed` 같은 "LLM이 잊어도 반드시 실행" 패턴. AHOY의 Hook은 차단에 초점, Open SWE는 보완/강제 실행에 초점
2. **실시간 메시지 주입**: 실행 중 외부에서 메시지를 주입하여 에이전트 행동 수정. AHOY는 스프린트 진행 중 외부 개입 메커니즘이 없음
3. **클라우드 샌드박스 격리**: 각 태스크가 완전 격리된 원격 환경. AHOY는 로컬 실행
4. **멀티 채널 호출**: Slack/Linear/GitHub/CLI 다중 진입점. AHOY는 Claude Code 세션에서만 실행
5. **LangSmith 관찰성**: 에이전트 행동의 전체 추적과 평가. AHOY의 Agent Trace 제안보다 성숙한 구현
6. **서브에이전트 오케스트레이션**: 복잡한 태스크를 하위 에이전트에게 자동 위임. AHOY는 단일 Generator

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리**: Open SWE는 동일 에이전트가 생성+자기검증. AHOY의 외부 모델 평가가 편향에 강함
2. **다중 모델 필수 컨센서스**: Open SWE는 단일 모델. AHOY의 2+ 외부 모델 합의가 더 견고
3. **스프린트 상태머신**: Open SWE는 단일 태스크 실행 후 PR 생성. AHOY의 반복적 rework 사이클이 품질 수렴에 유리
4. **파일 소유권 분리 / Generator 의견 strip**: Open SWE에는 없음
5. **계약 기반 개발**: Open SWE는 이슈/PR 설명이 유일한 명세. AHOY의 contract.md가 더 엄격한 공동 참조점

## 배울 만한 구체적 아이디어

### 1. 보완적 미들웨어 패턴 (Fallback Middleware)
- **현재 AHOY**: Hook은 차단/거부 위주
- **제안**: "Generator가 빠뜨린 작업을 자동으로 보완하는" 미들웨어 추가. 예: 테스트 파일 생성 누락 시 자동 생성 요청, 문서 업데이트 누락 시 알림
- **구현**: `hooks/fallback_middleware.py` — PostToolUse에서 generated 상태 진입 시 체크리스트 자동 검증

### 2. 실행 중 외부 메시지 주입 (Runtime Message Injection)
- **현재 AHOY**: 스프린트 진행 중 외부 개입 불가
- **제안**: eval_dispatch.py에 메시지 큐 추가. 사용자가 스프린트 실행 중 추가 지시/수정 사항 주입 가능
- **구현**: `eval_dispatch.py`에 Redis/파일 기반 메시지 큐 체크 로직

### 3. 에이전트 실행 관찰성 (Agent Observability)
- **현재 AHOY**: 실행 로그 수준
- **제안**: 모든 도구 호출, LLM 응답, 상태 전이를 구조화된 트레이스로 기록. 사후 분석 + 패턴 추출
- **구현**: `ahoy_trace.py` (신규) — OpenTelemetry 스팬 기반 기록, JSON Lines 출력

## AHOY 개선 제안 Top 3

### 1. 보완적 Hook 패턴 (Complementary Hook / Fallback Actions)
- **파일**: `hooks/fallback_actions.py` (신규), Hook 설정에 `fallback_actions` 카테고리 추가
- **구현**: generated 상태 진입 시 자동 체크리스트 실행 — (1) 테스트 파일 존재 여부, (2) 문서 업데이트 여부, (3) contract.md의 모든 요구사항 대응 코드 존재 여부. 누락 항목은 issues.json에 `type: "missing_deliverable"`로 자동 추가
- **효과**: Generator의 "빠뜨림" 패턴을 시스템이 자동 보완. 평가자 부담 경감

### 2. 스프린트 실행 중 사용자 개입 채널 (Runtime Intervention Channel)
- **파일**: `runtime_channel.py` (신규), `eval_dispatch.py` 수정
- **구현**: 스프린트 실행 중 `.ahoy/messages/` 디렉토리를 폴링. 사용자가 파일을 드롭하면 다음 평가 사이클에서 추가 지시로 주입. rework 시 Generator에게 추가 컨텍스트로 전달
- **효과**: 긴 스프린트에서 방향 수정 가능, 사용자 피드백 반영 속도 향상

### 3. 구조화된 에이전트 트레이스 시스템 (Structured Agent Trace)
- **파일**: `ahoy_trace.py` (신규), `eval_dispatch.py`에 트레이스 미들웨어 통합
- **구현**: 모든 eval_dispatch 호출(API 요청/응답), Hook 발동(규칙/결과), 상태 전이(before/after)를 OpenTelemetry 호환 스팬으로 기록. `traces/` 디렉토리에 스프린트별 JSONL 파일 생성. handoff 시 자동 요약
- **효과**: 실패 원인 사후 분석, 평가 패턴 추출, handoff 품질 향상
