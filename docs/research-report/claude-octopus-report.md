# Claude Octopus 분석 리포트

> 분석일: 2026-03-28 (9차)

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Claude Octopus |
| GitHub URL | https://github.com/nyldn/claude-octopus |
| 스타 | 2,100+ |
| 커밋 | 834+ |
| 언어 | Shell / TypeScript |
| 라이선스 | MIT |
| 플랫폼 | Claude Code 플러그인 |

## 핵심 아키텍처

Claude Octopus는 최대 8개 AI 프로바이더를 오케스트레이션하는 Claude Code 플러그인으로, **Double Diamond 워크플로우**와 **75% 컨센서스 품질 게이트**를 통해 멀티 LLM 협업을 구현한다.

### 8개 프로바이더 ("Tentacles")

| 프로바이더 | 역할 | 비용 |
|-----------|------|------|
| Codex (OpenAI) | 구현 깊이 + 코드 패턴 | OAuth (무료) |
| Gemini (Google) | 에코시스템 넓이 + 보안 리뷰 | OAuth (무료) |
| Perplexity | 실시간 웹 검색 + CVE 조회 | 유료 |
| OpenRouter | 100+ 모델 통합 API | 유료 |
| Copilot (GitHub) | 기존 구독 활용 | 기존 구독 |
| Qwen (Alibaba) | 무료 티어 (1,000-2,000 일일) | 무료 |
| Ollama | 로컬 프라이버시 LLM | 무료 |
| Claude (Anthropic) | 내장 오케스트레이션 엔진 | 기존 |

**핵심 가치**: 5개 프로바이더가 추가 비용 없이 사용 가능. 점진적 확장 가능.

### Double Diamond 워크플로우 (4단계)

UK Design Council의 더블 다이아몬드 방법론 기반:

1. **Discover** — 멀티 AI 리서치/탐색 (병렬 프로바이더 실행)
2. **Define** — 컨센서스 기반 요구사항 명확화
3. **Develop** — 품질 게이트 포함 구현
4. **Deliver** — 적대적 리뷰 + Go/No-Go 스코어링

### 75% 컨센서스 품질 게이트

- 활성 프로바이더 중 75% 이상 동의 시 진행
- 미달 시 구조화된 토론(debate) 개시
- 토론 후에도 미달 시 사람에게 에스컬레이션

### 적대적 리뷰 프로세스

- **Discover**: 병렬 프로바이더 실행
- **Define**: 순차 프로바이더 디스패치 (문제 범위 확정)
- **Deliver**: 적대적 교차 검증 (Delivery 단계)

### 크로스 모델 패턴 인식

한 프로바이더가 패턴을 식별하면 다른 프로바이더들이 동일 문제를 독립 평가. 불일치 시 구조화된 토론, 합의 시 다음 단계 진행.

### 47 커맨드 / 50 스킬 / 32 페르소나

- `/octo:embrace` — 전체 워크플로우 시작
- `/octo:factory` — 배치 생산
- `/octo:debate` — 구조화된 다모델 토론
- `/octo:research` — 멀티 AI 리서치
- `/octo:security` — 보안 감사
- 32개 페르소나: security-auditor, ui-ux-designer 등 의도 기반 자동 활성화

### Reaction Engine

명시적 커맨드 없이 자동 반응:
- CI 실패 자동 감지 + 대응
- 리뷰 코멘트 자동 처리
- 비활성 에이전트 감지

### MCP 서버 통합

10개 Octopus 도구를 MCP 프로토콜로 노출:
- Telegram, Discord, Signal 등 메시징 플랫폼 통합
- 플러그인 수정 없이 외부 도구 접근

## AHOY와 비교

### AHOY보다 나은 점

1. **8 프로바이더 오케스트레이션**: AHOY는 Codex+Gemini 2개 평가자. Claude Octopus는 8개 프로바이더를 유연하게 활용. 필요에 따라 프로바이더 추가/제거 가능

2. **75% 컨센서스 기반 유연한 합의**: AHOY의 "하나라도 fail → 최종 fail"은 엄격하지만 false positive에 취약. Octopus의 75% 합의는 노이즈를 허용하면서도 다수결 품질 보장

3. **비용 최적화 아키텍처**: 5개 프로바이더가 무료 — 평가 비용 대폭 절감. AHOY는 Codex+Gemini API 호출마다 비용 발생

4. **Reaction Engine (이벤트 기반 자동 대응)**: AHOY는 명시적 Hook 실행만 지원. Octopus는 CI 실패/리뷰 코멘트/에이전트 비활성 등 이벤트에 자동 반응

5. **구조화된 토론 메커니즘**: 불일치 시 `/octo:debate`로 다모델 구조화된 토론 실행. AHOY는 불일치 시 단순 fail 처리

6. **Double Diamond 체계적 워크플로우**: 디자인 씽킹 기반 발산→수렴→발산→수렴 4단계는 AHOY의 선형 파이프라인보다 탐색적 문제에 적합

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리**: Octopus는 동일 Claude Code 세션에서 모든 프로바이더 호출. AHOY는 eval_dispatch.py라는 별도 프로세스로 완전 분리

2. **Hook 기반 하드 차단**: Octopus의 품질 게이트는 워크플로우 스크립트 수준. AHOY는 PreToolUse/PostToolUse Hook으로 에이전트 런타임에서 직접 강제, 우회 불가

3. **파일 소유권 분리**: Octopus에는 파일 단위 쓰기 권한 분리 없음. issues.json을 Claude가 직접 수정할 수 있는 구조

4. **Generator 의견 strip**: Octopus는 모델 출력을 그대로 전달하여 컨센서스 도출. AHOY의 주관적 판단 기계적 제거 메커니즘 없음

5. **스프린트 상태머신**: Octopus의 Double Diamond은 4단계이지만 상태 전이 규칙의 기계적 강제가 AHOY만큼 엄격하지 않음

6. **엄격한 최소 컨센서스**: 75% 합의는 유연하지만, 보안 관련 이슈에서는 AHOY의 "하나라도 fail → 최종 fail"이 더 안전

## 배울 만한 구체적 아이디어

### 1. 컨센서스 임계값 도메인별 차등 적용

**적용 대상**: `eval_dispatch.py` 컨센서스 로직

```python
CONSENSUS_THRESHOLDS = {
    "security": 1.0,      # 보안: 만장일치 (현재 AHOY 방식)
    "correctness": 1.0,   # 정확성: 만장일치
    "style": 0.5,         # 스타일: 과반수
    "performance": 0.75,  # 성능: 75%
}

def evaluate_consensus(findings: list[EvalResult], domain: str) -> bool:
    threshold = CONSENSUS_THRESHOLDS.get(domain, 1.0)
    pass_rate = sum(1 for f in findings if f.passed) / len(findings)
    return pass_rate >= threshold
```

### 2. Reaction Engine (이벤트 기반 자동 대응)

**적용 대상**: Hook 시스템 확장

```python
# 이벤트 감지 + 자동 대응 레지스트리
REACTIONS = {
    "ci_failure": lambda ctx: trigger_rework(ctx, reason="CI failed"),
    "coverage_drop": lambda ctx: add_issue(ctx, "coverage regression"),
    "stale_sprint": lambda ctx: emit_warning(ctx, "sprint idle > 30min"),
}

def process_event(event_type: str, context: dict):
    if handler := REACTIONS.get(event_type):
        handler(context)
```

### 3. 프로바이더 비용 라우팅

**적용 대상**: `eval_dispatch.py` 모델 선택

```python
# 태스크 중요도별 프로바이더 선택
PROVIDER_TIERS = {
    "critical": ["codex", "gemini"],       # 보안/정확성: 프리미엄 모델
    "standard": ["qwen", "copilot"],       # 스타일/성능: 무료/저비용
    "exploratory": ["ollama"],             # 탐색적 평가: 로컬
}
```

### 4. 구조화된 토론 프로토콜

**적용 대상**: eval_dispatch.py 불일치 해소

현재 AHOY는 평가자 불일치 시 단순 fail. 토론 라운드 추가:
```python
async def resolve_disagreement(eval_a: EvalResult, eval_b: EvalResult) -> EvalResult:
    # 라운드 1: 각 평가자에게 상대방 findings 제시
    reeval_a = await codex.reevaluate(eval_a, counterpoint=eval_b.findings)
    reeval_b = await gemini.reevaluate(eval_b, counterpoint=eval_a.findings)
    # 라운드 2: 수렴 확인
    if reeval_a.agrees_with(reeval_b):
        return merge(reeval_a, reeval_b)
    return EvalResult(passed=False, reason="Persistent disagreement")
```

---

## AHOY 개선 제안 Top 3

### 1. 도메인별 차등 컨센서스 임계값

**구현 방향**: issues.json의 각 이슈를 도메인(security/correctness/style/performance)별로 분류. 도메인별 컨센서스 임계값 적용 — 보안/정확성은 만장일치 유지, 스타일/성능은 75% 합의로 완화. false positive 감소 + rework 효율 향상.

**변경 파일**:
- `eval_dispatch.py` — 도메인별 컨센서스 로직
- 신규 `.ahoy/consensus_thresholds.json` — 도메인별 임계값 설정
- 평가 프롬프트 — 이슈별 도메인 분류 필드 추가

### 2. 평가자 불일치 시 구조화된 토론 프로토콜

> **v0.2.0 구현 완료** — `eval_dispatch.py:build_round2_prompt()` 불일치 시 상대방 findings 제시 후 재평가 1회 (2-Round 교차 검증)

**구현 방향**: Codex와 Gemini가 불일치할 때 단순 fail 대신, 상대방 findings를 제시하고 재평가하는 1회 추가 라운드 도입. 재평가 후에도 불일치 시 fail. 토큰 비용은 증가하지만 false positive 대폭 감소.

**변경 파일**:
- `eval_dispatch.py` — `resolve_disagreement()` 함수 추가
- 평가 프롬프트 — "상대방이 이런 문제를 찾았는데 동의하는가?" 재평가 프롬프트

### 3. Reaction Engine (이벤트 기반 자동 대응)

**구현 방향**: Hook 시스템에 이벤트 리스너 추가. CI 실패/커버리지 하락/스프린트 비활성 등 이벤트 감지 시 자동 rework 트리거 또는 경고 발생. `.ahoy/reactions.json`으로 이벤트-액션 매핑 설정.

**변경 파일**:
- 신규 `reaction_engine.py` — 이벤트 감지 + 액션 디스패치
- 신규 `.ahoy/reactions.json` — 이벤트-액션 매핑
- `hooks/post_tool_use.py` — 이벤트 발행 연동
