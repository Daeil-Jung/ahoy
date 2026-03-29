# SentinelOne Adversarial Consensus Engine (Gauntlet) 분석 리포트

> 분석일: 2026-03-28 (5차)

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Adversarial Consensus Engine (Gauntlet) |
| URL | https://www.sentinelone.com/labs/building-an-adversarial-consensus-engine-multi-agent-llms-for-automated-malware-analysis/ |
| GitHub | 공개 리포지토리 없음 (SentinelOne Labs 블로그 기반 아키텍처) |
| 프레임워크 | OpenClaw (오픈소스 에이전트 프레임워크) |
| 모델 | Claude Opus 4.6 (오케스트레이터), Claude Sonnet 4.6 (서브에이전트) |
| 핵심 키워드 | 3단계 파이프라인, Active Rejection Mandate, 역순 재검증, 결정론적 브릿지, 토큰 캐싱 |

## 핵심 아키텍처

### 3단계 파이프라인

```
Phase 1: Sequential Tool Analysis (초기 추출)
    radare2 → Ghidra → Binary Ninja → IDA Pro
    ├─ 각 에이전트: 이전 결과 검증 + 신규 발견 추가
    └─ Shared Context: 메모리 내 구조화 문서 (동적 주입)
         ↓
Phase 2: The Gauntlet (적대적 리뷰) ← 역순 실행
    Ghidra reviews IDA → Binary Ninja reviews Ghidra → IDA reviews Binary Ninja
    ├─ Active Rejection Mandate: AGREE/DISAGREE 필수 판정
    ├─ 거부 시 rationale 필수 기록
    └─ 생존한 findings만 Phase 3으로 전달
         ↓
Phase 3: Report Synthesis (보고서 생성)
    ├─ 전용 report-writer 에이전트
    └─ 모든 주장에 가상 주소 + 디컴파일 스니펫 앵커링
```

### Active Rejection Mandate

- 모든 서브에이전트는 "고도로 회의적인 피어 리뷰어"로 작동
- 출력 스키마에 `Consensus` 필드 강제: `AGREE` 또는 `DISAGREE`만 허용
- 거부된 주장은 별도 테이블에 거부 도구 + 이유 기록
- **실제 효과**: radare2가 C2 엔드포인트를 `/api/req_res` (밑줄)로 추출 → Ghidra가 `/api/req/res` (슬래시)로 정정 감지

### 결정론적 브릿지 스크립트 (MCP 대신 선택)

- 40줄 셸 스크립트 (IDA), Python 래퍼 (Binary Ninja)
- **핵심 원칙**: "결정론적 브릿지는 모든 것을 추출하도록 프로그래밍됨 — 모든 문자열, 모든 임포트, 모든 크로스 레퍼런스, 모든 함수 시그니처를 한 번에"
- MCP의 대화형 접근(LLM이 무엇을 질의할지 결정)보다 일괄 추출이 일관성과 완전성에서 우수

### 토큰 경제학

| 단계 | 토큰 소비 | 최적화 |
|------|-----------|--------|
| Phase 1 | 100,000+ / 에이전트 | 프롬프트 캐싱 (입력 비용 90% ↓, 레이턴시 85% ↓) |
| Phase 2 | ~56,000 (Phase 1 대비 44,000 ↓) | 정제된 Shared Context만 평가 |
| 모델 배정 | Opus=오케스트레이터, Sonnet=서브에이전트 | 30-50% 비용 증가, 품질 대폭 향상 |

### 오케스트레이터 복원력

- API 타임아웃으로 서브에이전트 사망 시, 오케스트레이터가 침묵 감지
- Shared Context 보존 → 사망 에이전트 재생성 → 중단 지점부터 재개
- **전체 파이프라인 재시작 불필요**

## AHOY와 비교

### AHOY보다 나은 점

1. **Active Rejection Mandate (강제 거부 메커니즘)**: AGREE/DISAGREE 이진 판정을 스키마 수준에서 강제. AHOY의 평가자는 pass/fail을 반환하지만, 명시적 "반박 강제" 프롬프트 없음
2. **역순 재검증 (Phase 2 Gauntlet)**: Phase 1의 결과를 다른 순서로 재검증하여 순서 편향(order bias) 제거. AHOY는 동일 프롬프트로 동시 평가하므로 순서 편향 통제 없음
3. **결정론적 브릿지의 완전성 보장**: 도구가 "무엇을 질의할지" 결정하는 것이 아니라 "모든 것을 일괄 추출". AHOY의 eval_dispatch.py가 평가 대상을 선택하는 과정에서 누락 가능성 존재
4. **프롬프트 캐싱 기반 토큰 최적화**: 정적 컨텍스트를 캐싱하여 Phase 2에서 44,000 토큰 절감. AHOY는 rework 시 동일 파일을 매번 재전송
5. **오케스트레이터 상태 보존 및 복구**: 서브에이전트 사망 시 자동 복구. AHOY는 API 실패 시 수동 재시도 필요

### AHOY가 더 나은 점

1. **코드 생성 특화 워크플로우**: Gauntlet은 정적 분석(멀웨어) 특화. AHOY의 planned→contracted→generated→passed 사이클은 코드 생성-검증에 최적화
2. **파일 소유권 분리**: Gauntlet의 Shared Context는 모든 에이전트가 읽기/쓰기 가능. AHOY의 issues.json 쓰기 권한 분리가 더 엄격
3. **Hook 기반 하드 차단**: Gauntlet은 오케스트레이터의 소프트 제어에 의존. AHOY의 PreToolUse Hook은 Claude 런타임 수준에서 우회 불가능한 차단
4. **계약 기반 개발**: contract.md로 Generator-Evaluator 공통 참조점 제공. Gauntlet은 도구별 출력만 참조
5. **Generator 의견 strip**: Gauntlet의 각 에이전트는 자유롭게 해석을 추가. AHOY는 gen_report에서 주관적 판단을 제거

## 배울 만한 구체적 아이디어

### 1. Active Rejection Mandate를 eval_dispatch.py에 적용 (최고 우선순위)

평가 프롬프트에 AGREE/DISAGREE 필수 필드 추가:

```python
EVAL_SCHEMA = {
    "verdict": {"type": "string", "enum": ["AGREE", "DISAGREE"]},
    "rationale": {"type": "string", "minLength": 50},
    "evidence": {"type": "string"},  # 코드 위치/스니펫 필수
    "findings": [...]
}
```

각 평가자가 반드시 동의 또는 반대를 명시하게 하여, 무의미한 "대체로 괜찮음" 응답 차단.

**적용 파일**: `eval_dispatch.py` — 평가 프롬프트 및 응답 파싱 로직 수정

### 2. 역순 재검증 라운드

rework 발생 시 평가자 순서를 역전:

- 1차 평가: Codex → Gemini (순서)
- rework 후 2차 평가: Gemini → Codex (역순, 이전 결과 참조)

순서 편향을 제거하고 두 번째 평가자가 첫 번째의 findings를 비판적으로 재검토.

**적용 파일**: `eval_dispatch.py` — 평가자 실행 순서 관리 로직 추가

### 3. 프롬프트 캐싱을 활용한 rework 비용 절감

미변경 파일의 컨텍스트를 캐싱하여 rework 시 변경 파일만 재전송:

```python
# rework 시 캐시 활용
cached_hash = hash(unchanged_files + eval_prompt)
if cached_hash in eval_cache:
    # 미변경 파일 평가 결과 재사용
    pass
else:
    # 변경 파일만 새로 평가
    pass
```

**적용 파일**: `eval_dispatch.py` — 파일 해시 기반 캐시 레이어 추가

---

## AHOY 개선 제안 Top 3

1. **Active Rejection Mandate 도입**

> **v0.2.0 구현 완료** — `eval_dispatch.py:build_eval_prompt()` Active Rejection 지시 + Forced Objection 프롬프트 적용

`eval_dispatch.py`의 평가 프롬프트에 AGREE/DISAGREE 이진 필드를 JSON 스키마로 강제. 평가자가 "대체로 괜찮음" 같은 모호한 응답을 할 수 없게 하여 평가 품질 즉시 향상. 구현 비용 매우 낮음 (프롬프트 + 파싱 변경만)

2. **역순 재검증 (Gauntlet Pattern)** — rework 발생 시 평가자 순서를 역전하여 Phase 2 실행. 첫 번째 평가자의 findings를 두 번째가 비판적으로 검토. 순서 편향 제거 + 평가 정밀도 향상. `eval_dispatch.py`에 `reverse_order` 파라미터 추가

3. **오케스트레이터 상태 보존 및 자동 복구** — API 타임아웃/실패 시 현재 Shared Context(sprint_memory/ 내용)를 보존하고 실패한 평가 모델만 재시도. `eval_dispatch.py`에 checkpoint/resume 로직 추가. 스프린트 중단 방지 + API Circuit Breaker 제안과 결합
