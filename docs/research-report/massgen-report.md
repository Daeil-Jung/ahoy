# MassGen 분석 리포트

> 분석일: 2026-03-28 (3차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | MassGen |
| GitHub URL | https://github.com/massgen/MassGen |
| 스타 | 893 |
| 최근 릴리스 | v0.1.68 (2026-03-25) — **매우 활발** |
| 라이선스 | 미확인 |
| 핵심 키워드 | 멀티 에이전트, 컨센서스, 반복 정제, 투표, TUI |

## 핵심 아키텍처

### 분산 오케스트레이션 + 컨센서스

```
Coordinator
  ├── Agent A ──┐
  ├── Agent B ──┼── Shared Collaboration Hub ── Vote ── Consensus
  └── Agent C ──┘
```

### 핵심 원칙: 완전 중복 + 집단 정제

1. **모든 에이전트가 전체 문제를 독립적으로 해결**
2. **상호 관찰**: 에이전트가 서로의 작업을 관찰하고 비평
3. **반복 정제**: 새로운 인사이트 발견 시 에이전트가 작업 재시작 가능
4. **자연 수렴**: 충분한 안정성에 도달하면 투표
5. **집단 검증**: 단순 다수결이 아닌 "최선의 집단 검증된 답"

### 체크포인트 모드 (v0.1.68)

```
Main Agent (계획 수립)
     ↓
Team Instances (위임 실행)
     ↓
Checkpoint (중간 결과 저장)
     ↓
다음 단계로 진행
```

- 메인 에이전트가 혼자 계획 수립
- 신선한 팀 인스턴스에게 위임
- 각 단계의 중간 결과를 체크포인트로 저장

### LLM API Circuit Breaker

- Rate limit 자동 감지
- 장애 시 자동 대기/재시도
- 회로 차단기 패턴으로 API 안정성 확보

### TUI 시각화

- Textual 기반 인터랙티브 터미널 UI
- 타임라인, 에이전트 카드, 투표 추적
- 실시간 진행 상황 모니터링

## AHOY 대비 비교

### MassGen이 AHOY보다 나은 점

1. **집단 정제 기반 컨센서스**: 단순 pass/fail이 아닌, 에이전트 간 상호 비평과 반복 정제를 통한 자연 수렴. AHOY는 독립 평가 후 이진 합의
2. **에이전트 간 실시간 관찰**: 에이전트가 서로의 작업을 관찰하고 인사이트를 공유. AHOY의 평가자들은 서로의 결과를 보지 못함
3. **체크포인트 모드**: 대규모 작업을 단계별로 분리하여 신선한 에이전트에게 위임. AHOY의 컨텍스트 리셋(3 스프린트)보다 세밀
4. **Circuit Breaker**: API 장애에 대한 자동 대응. AHOY는 API 실패 시 수동 처리
5. **TUI 대시보드**: 실시간 에이전트 상태/투표 시각화. AHOY에는 UI 없음
6. **적응적 재시작**: 새 인사이트 발견 시 에이전트가 자발적으로 작업 재시작. AHOY의 rework는 평가 실패 시에만

### AHOY가 MassGen보다 나은 점

1. **Generator-Evaluator 분리**: MassGen은 모든 에이전트가 생성+평가를 겸함. 자기평가 편향 존재
2. **하드 차단**: MassGen의 컨센서스는 "자연 수렴". 규칙 위반을 물리적으로 차단하지 않음
3. **파일 소유권 분리**: MassGen은 모든 에이전트가 동일 자원 접근
4. **Generator 의견 strip**: MassGen은 에이전트 간 비평에 주관적 의견 포함
5. **스프린트 상태머신**: MassGen은 유연한 반복 정제. 명시적 상태 전이 규칙 없음
6. **계약 기반 개발**: 공통 참조 문서 기반 합의 체계 없음

### 배울 만한 구체적 아이디어

1. **평가자 간 교차 검증 (Cross-pollination)**
   - Codex와 Gemini의 평가 결과를 서로에게 보여주고 재평가 기회 제공
   - 1라운드: 독립 평가 → 2라운드: 상대 결과 참조 후 최종 판단
   - 기존 제안 "Debate Mode 평가"의 구체적 구현 방식

2. **Circuit Breaker 패턴**
   - `eval_dispatch.py`에 연속 API 실패 시 자동 대기/모델 폴백 로직
   - 연속 3회 실패 → 30초 대기 → 재시도 → 대체 모델 사용
   - 기존 제안 "평가 프로세스 Watchdog"의 구체적 구현

3. **Textual TUI 대시보드**
   - Python `textual` 라이브러리로 터미널 UI 구현
   - 스프린트 상태, rework 횟수, 평가 결과 실시간 표시
   - 기존 제안 "실시간 스프린트 상태 조회 CLI"의 구체적 참조

---

## AHOY 개선 제안 Top 3

### 1. 평가자 간 교차 검증 (2라운드 평가)

> **v0.2.0 구현 완료** — `eval_dispatch.py:build_round2_prompt()` + `check_verdict_conflict()` 불일치 시 Round 2 자동 실행, 쿼럼 유지 검증

- **구현 대상**: `eval_dispatch.py` (컨센서스 로직 확장)
- **변경 내용**: 1라운드에서 Codex/Gemini 독립 평가 → 불일치 시 2라운드에서 상대의 findings를 컨텍스트로 포함하여 재평가 → 최종 판단
- **효과**: 평가자 간 "놓친 이슈"를 상호 보완. 단순 AND 합의보다 정밀한 평가
- **참조**: MassGen 상호 관찰/비평, Star Chamber Debate Mode

### 2. API Circuit Breaker
- **구현 대상**: `eval_dispatch.py` (API 호출 래퍼)
- **변경 내용**: 연속 실패 카운터 + 백오프 로직 + 모델 폴백 체인. `CircuitBreaker(max_failures=3, reset_timeout=30, fallback_model="gemini-flash")` 클래스 구현
- **효과**: API 불안정 시 자동 복구. 스프린트 중단 방지
- **참조**: MassGen Circuit Breaker, 기존 제안 "평가 프로세스 Watchdog"

### 3. Textual TUI 스프린트 대시보드
- **구현 대상**: 새 파일 `ahoy_dashboard.py`
- **변경 내용**: Python `textual` 라이브러리로 터미널 대시보드 구현. 현재 스프린트 상태, 이슈 목록, rework 횟수, 평가 히스토리, 모델별 pass/fail 통계를 실시간 표시
- **효과**: 스프린트 진행 상황을 직관적으로 파악. 문제 조기 발견
- **참조**: MassGen Textual TUI, Oh-My-Claudecode 대시보드
