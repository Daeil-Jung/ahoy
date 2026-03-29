# Aragora (Synaptent) 분석 리포트

> 분석일: 2026-03-28 (10차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Aragora |
| GitHub URL | https://github.com/synaptent/aragora |
| 스타 | ~500+ (추정) |
| 최근 커밋 | 2026년 3월 활성 |
| 라이선스 | 오픈소스 |
| 언어 | Python |

## 핵심 아키텍처

### 개요
Aragora는 "Omnivorous Multi Agent Decision Making Engine"으로, 9+ LLM 프로바이더(Claude, GPT, Gemini, Grok, Mistral, DeepSeek, Qwen, Kimi, 로컬 모델)를 Propose/Critique/Revise 구조화된 토론으로 오케스트레이션하는 멀티 에이전트 컨센서스 엔진이다.

### 구조
```
[입력 (모든 소스)] → [Propose Phase]
                         ↓
              [각 에이전트 독립 응답 생성]
                         ↓
                  [Critique Phase]
              [에이전트 간 상호 비판 + Severity 점수]
                         ↓
                  [Revise Phase]
              [비판 반영하여 응답 수정]
                         ↓
              [Consensus Decision]
              (majority/unanimous/judge/none)
                         ↓
              [Trickster 검증]
              [공허한 합의 감지]
                         ↓
              [ELO 업데이트 + Brier Score]
```

### 핵심 특징

1. **Propose/Critique/Revise 프로토콜**: 논제→반제→합제 3단계 구조화된 토론
2. **4종 컨센서스 모드**: majority(다수결), unanimous(만장일치), judge(판사), none(합의 불필요)
3. **Trickster (공허 합의 감지)**: 모델들이 진정한 추론 없이 동의하는 "hollow consensus" 자동 탐지
4. **ELO 랭킹**: 에이전트 성능을 ELO 점수로 지속 추적
5. **Brier Score (보정 점수)**: 예측 정확도를 정량화하여 에이전트 신뢰도 측정
6. **4-Tier Continuum Memory**: fast/medium/slow/glacial 4계층 메모리 + Knowledge Mound (42 어댑터)
7. **Nomic Loop (자율 자기개선)**: 에이전트가 코드베이스 개선을 토론→설계→구현→테스트, 인간 승인 게이트 포함
8. **9+ LLM 프로바이더 지원**: Claude, GPT, Gemini, Grok, Mistral, DeepSeek, Qwen, Kimi, 로컬
9. **Dissent Trail**: 불일치 기록을 보존하여 인간 판단이 필요한 영역 명시

## AHOY와 비교

### AHOY보다 나은 점

1. **Trickster (공허 합의 감지)**: 평가자들이 진정한 분석 없이 동의하는 패턴을 자동 감지. AHOY는 아첨 감지 메커니즘이 없음
2. **ELO 기반 평가자 성능 추적**: 평가자의 누적 성능을 정량화. AHOY는 평가자 성능 추적 없음
3. **Brier Score 보정**: 예측 정확도를 통계적으로 측정. AHOY는 평가 품질의 정량적 측정 없음
4. **4종 컨센서스 모드**: 상황별 합의 방식 선택 가능. AHOY는 만장일치 단일 모드
5. **Propose/Critique/Revise 3단계**: 체계적 비판-수정 사이클. AHOY는 독립 평가 → 합의 2단계
6. **4-Tier Memory**: 장기 학습 + 지식 누적. AHOY는 handoff 수준의 단기 기억만 보유
7. **Dissent Trail**: 불일치 의견의 체계적 보존. AHOY는 소수 의견 기록 없음
8. **Nomic Loop**: 자기 개선 자율 사이클. AHOY는 수동 개선만 지원

### AHOY가 더 나은 점

1. **Generator-Evaluator 물리적 분리**: Aragora는 동일 프레임워크 내 생성+평가 가능. AHOY는 완전 분리
2. **Hook 기반 하드 차단**: Aragora는 소프트 규칙. AHOY는 PreToolUse/PostToolUse 하드 차단
3. **파일 소유권 분리**: Aragora에는 파일 수준 접근 제어 없음
4. **Generator 의견 strip**: Aragora는 의견 필터링 없음
5. **스프린트 상태머신**: Aragora는 토론 기반 자유 실행. AHOY는 엄격한 상태 전이
6. **rework 제한**: Aragora는 토론 라운드 제한만. AHOY는 구조화된 3회 rework 사이클
7. **코드 생성 특화**: Aragora는 범용 의사결정. AHOY는 코드 생성-평가에 최적화

## 배울 만한 구체적 아이디어

### 1. Trickster (공허 합의 감지) 패턴
```python
# eval_dispatch.py에 추가
class HollowConsensusDetector:
    def detect(self, evaluations):
        """평가자들의 동의가 진정한 분석에 기반하는지 검증"""
        # 1. 모든 평가자가 pass이고 이슈가 0개면 의심
        all_pass = all(e["result"] == "pass" for e in evaluations)
        no_issues = sum(len(e.get("issues", [])) for e in evaluations) == 0

        # 2. 평가 근거의 고유성 검사 (유사도 높으면 복사 의심)
        rationales = [e["rationale"] for e in evaluations]
        similarity = compute_similarity(rationales)

        # 3. 최근 N 스프린트의 pass 비율 추적
        recent_pass_rate = self.get_rolling_pass_rate(window=10)

        if all_pass and no_issues and similarity > 0.85:
            return {"hollow": True, "reason": "identical_rationale"}
        if recent_pass_rate > 0.95:
            return {"hollow": True, "reason": "suspicious_pass_rate"}
        return {"hollow": False}
```

### 2. ELO 기반 평가자 신뢰도
```python
# eval_dispatch.py에 추가
class EvaluatorELO:
    def __init__(self):
        self.ratings = {"codex": 1200, "gemini": 1200}

    def update(self, evaluator, predicted_correct):
        """벤치마크 정답 대비 평가 정확도로 ELO 업데이트"""
        K = 32
        expected = 1 / (1 + 10 ** ((1200 - self.ratings[evaluator]) / 400))
        actual = 1.0 if predicted_correct else 0.0
        self.ratings[evaluator] += K * (actual - expected)
```

### 3. Dissent Trail (불일치 기록 보존)
```python
# issues.json에 dissent_trail 필드 추가
{
    "consensus": "fail",
    "issues": [...],
    "dissent_trail": [
        {
            "evaluator": "codex",
            "original_verdict": "pass",
            "final_verdict": "fail",
            "reason_changed": "gemini의 보안 이슈 지적에 동의"
        }
    ]
}
```

---

## AHOY 개선 제안 Top 3

### 1. 공허 합의 감지기 (Trickster 패턴)
- **파일**: `eval_dispatch.py`
- **변경**: 컨센서스 산출 후 "hollow consensus" 검증 단계 추가. 모든 pass + 이슈 0개 + 높은 근거 유사도 시 자동 재평가 트리거. 최근 N 스프린트 pass 비율 이동 평균 추적
- **효과**: 아첨 편향(sycophancy)의 구조적 감지, 평가 품질 안정화

### 2. 평가자 ELO 성능 추적
- **파일**: 신규 `.ahoy/evaluator_stats.json`, `eval_dispatch.py`
- **변경**: 알려진 정답이 있는 벤치마크 태스크로 평가자 정확도 추적. ELO 점수 누적 관리. 저신뢰 평가자에 대해 3번째 평가자 자동 추가
- **효과**: 평가자 품질 정량화, 평가 편향 자동 감지 및 보정

### 3. Dissent Trail (불일치 기록) 보존
- **파일**: `eval_dispatch.py`, `issues.json` 스키마
- **변경**: 컨센서스 과정에서 탈락된 소수 의견을 `dissent_trail` 배열로 보존. 동일 이슈가 3회 이상 소수 의견으로 등장 시 자동 승격
- **효과**: 반복 등장하는 진짜 이슈 포착, 다수결의 맹점 보완
