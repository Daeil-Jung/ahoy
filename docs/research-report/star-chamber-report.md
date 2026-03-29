# The Star Chamber (Multi-LLM Consensus for Code Quality) 분석 리포트

> 분석일: 2026-03-27

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | The Star Chamber |
| URL | https://blog.mozilla.ai/the-star-chamber-multi-llm-consensus-for-code-quality/ |
| 제작 | Mozilla AI |
| 유형 | Claude Code Skill |
| 최근 활동 | 2026년 활발 |

## 핵심 아키텍처

### 3단계 컨센서스 프로세스
1. **Context Gathering**: 코드, CLAUDE.md, ARCHITECTURE.md에서 프로젝트 규칙 수집 + 구조화된 리뷰 프롬프트 생성
2. **Parallel Distribution**: 모든 설정된 프로바이더에 동시 전송. 각 모델이 독립적으로 리뷰
3. **Consensus Aggregation**: 결과를 3단계로 분류:
   - **Consensus issues** (모든 프로바이더 지적) → 최고 신뢰도
   - **Majority issues** (2+ 프로바이더) → 높은 신뢰도
   - **Individual observations** (1개 프로바이더) → 전문적 인사이트 또는 노이즈

### 모델 구성
기본: Claude, GPT, Gemini (프로바이더 리스트 설정 가능)

### 리뷰 모드
- **Parallel Mode** (기본): 모든 프로바이더가 단일 라운드에서 독립 리뷰
- **Debate Mode** (`--debate --rounds N`): 다수 라운드에 걸쳐 익명 합성 공유. Chatham House Rule 적용으로 귀속 편향 방지

### 구조화된 출력
자유 텍스트가 아닌 JSON 타입 필드 (severity, location, category, description, suggested fixes)로 반환 → 안정적 집계 가능

## AHOY와 비교

### AHOY보다 나은 점
1. **Debate Mode**: 다수 라운드 토론으로 깊은 분석. AHOY는 단일 라운드 독립 평가만
2. **3단계 신뢰도 분류**: Consensus/Majority/Individual로 발견 사항의 중요도 자동 분류. AHOY는 all-pass/any-fail 이진
3. **Chatham House Rule**: 익명 합성으로 귀속 편향 방지. 모델 A의 의견이 모델 B에 영향 주지 않음
4. **구조화된 리뷰 출력**: JSON 스키마 기반으로 일관된 결과 포맷. AHOY의 gen_report 포맷보다 정형화
5. **CLAUDE.md/ARCHITECTURE.md 연동**: 프로젝트 규칙을 자동으로 리뷰 컨텍스트에 포함

### AHOY가 더 나은 점
1. **전체 개발 사이클 관리**: Star Chamber는 코드 리뷰만 담당. AHOY는 계획→계약→생성→평가 전체 관리
2. **Generator-Evaluator 구조적 분리**: Star Chamber는 리뷰 도구일 뿐 생성자를 제한하지 않음
3. **Hook 기반 하드 차단**: 없음. 소프트 리뷰 결과만 제공
4. **파일 소유권 분리**: 없음
5. **스프린트 상태머신**: 없음. 단발성 리뷰 도구
6. **rework 사이클 관리**: 없음
7. **컨텍스트 리셋**: 없음

### 배울 만한 구체적 아이디어
1. **Debate Mode 라운드**: eval_dispatch.py에서 첫 라운드 평가 후 결과를 익명화하여 2차 라운드 투입 → 더 깊은 분석
2. **3단계 이슈 분류**: Consensus/Majority/Individual 분류로 rework 우선순위 자동 결정
3. **구조화된 평가 스키마**: 평가 결과를 severity/location/category/description/fix JSON으로 표준화
4. **Chatham House Rule 적용**: 평가자 간 익명성 보장으로 앵커링 효과 차단

---

## AHOY 개선 제안 Top 3

### 1. Debate Mode 평가 (다라운드 적대적 토론)

> **v0.2.0 구현 완료** — `eval_dispatch.py:build_round2_prompt()` verdict conflict 시 2-Round 교차 검증. 비용 통제를 위해 최대 2라운드 제한

**현재 문제**: 단일 라운드 독립 평가로 표면적 이슈만 발견될 수 있음
**구현 방향**:
- `eval_dispatch.py`에 `debate_rounds` 파라미터 추가 (기본값 1, 옵션 2-3)
- 1라운드: 각 모델 독립 평가
- 2라운드: 1라운드 결과를 익명화하여 다른 모델에게 전달 + "이 평가에서 놓친 점을 찾아라" 지시
- 3라운드 (선택): 최종 합성. 모든 모델이 전체 발견 사항에 대해 동의/반대 투표
- `config.json`에서 `debate_mode: true/false`, `debate_rounds: N` 설정

### 2. 이슈 신뢰도 3단계 분류 시스템
**현재 문제**: 모든 이슈가 동일 중요도로 처리되어 rework 우선순위 판단 어려움
**구현 방향**:
- `issues.json`의 각 이슈에 `agreement_level` 필드 추가: "consensus" | "majority" | "individual"
- consensus: 모든 평가자 지적 → 즉시 수정 필수
- majority: 과반 지적 → 수정 권장
- individual: 한 평가자만 지적 → 검토 후 결정
- Generator의 rework 시 consensus 이슈부터 우선 해결하도록 gen_report에 우선순위 표시

### 3. 구조화된 평가 결과 스키마 표준화
**현재 문제**: 평가 결과 포맷이 모델별로 다를 수 있어 파싱 불안정
**구현 방향**:
- `schemas/eval_result.json` 신규 생성: 표준 평가 결과 JSON 스키마 정의
```json
{
  "severity": "critical|major|minor|info",
  "location": {"file": "...", "line": N},
  "category": "bug|security|performance|style|logic",
  "description": "...",
  "suggested_fix": "...",
  "confidence": 0.0-1.0
}
```
- eval_dispatch.py에서 각 모델 응답을 스키마로 정규화하는 파서 추가
- 비정형 응답 시 재요청 로직 포함
