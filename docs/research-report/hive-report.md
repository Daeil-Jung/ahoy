# Hive (aden-hive) 분석 리포트

> 분석일: 2026-03-28 (10차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Hive |
| GitHub URL | https://github.com/aden-hive/hive |
| 스타 | 7,900+ |
| 포크 | 4,400+ |
| 최근 커밋 | 2026년 3월 (매우 활발) |
| 라이선스 | 오픈소스 |
| 언어 | Python |

## 핵심 아키텍처

### 개요
Hive는 "Outcome-driven agent development framework that evolves"로, AI 에이전트의 프로덕션 런타임 하네스다. 자연어 목표를 입력하면 코딩 에이전트(queen)가 에이전트 그래프와 연결 코드를 생성하고 실행한다.

### 구조
```
[자연어 목표] → [Queen (코딩 에이전트)]
                      ↓
            [에이전트 그래프 생성]
                      ↓
            [AgentRuntime 실행]
              ├── State Isolation
              ├── Checkpoint Recovery
              ├── Cost Enforcement
              └── Real-time Observability
                      ↓
            [실패 시 자동 진화 & 재배포]
```

### 핵심 특징

1. **4단계 상태 격리 수준**: shared(통합 세션), isolated(분리 세션), synchronized(잠금 공유), 독립 ExecutionStream
2. **체크포인트 기반 크래시 복구**: 3계층 resume 프롬프트, 시간 여행 디버깅, 일시정지 지점 복원
3. **세분화된 비용 관리**: 팀/에이전트/워크플로우 수준 예산 제한, 자동 모델 다운그레이드, 실시간 비용 추적
4. **자동 진화 (Self-Evolution)**: 에이전트 실패 시 실패 데이터 캡처 → 그래프 진화 → 자동 재배포
5. **100+ LLM 프로바이더**: LiteLLM 통합으로 OpenAI, Anthropic, Gemini, DeepSeek 등 지원
6. **Session Manager**: 동시 세션 지원, 재연결, 세션 격리
7. **Human-in-the-Loop**: 내장 HITL 노드, 브라우저 제어, 자격증명 관리
8. **병렬 실행**: 독립 태스크 동시 처리

## AHOY와 비교

### AHOY보다 나은 점

1. **체크포인트 기반 복구 시스템**: 에이전트 크래시 시 마지막 체크포인트에서 자동 복원. AHOY는 rework 사이클은 있지만 중간 크래시 복구가 없음
2. **세분화된 비용 관리**: 팀/에이전트/워크플로우 수준 예산 + 자동 모델 다운그레이드. AHOY는 토큰 예산 관리 없음
3. **자동 진화 메커니즘**: 실패 데이터를 학습하여 에이전트 그래프 자체를 자동 수정. AHOY는 rework로 코드만 수정, 프로세스 자체는 정적
4. **다중 격리 수준**: 4단계 상태 격리로 에이전트 간 간섭 방지. AHOY는 단일 세션 실행
5. **프로덕션 관측 가능성**: 실시간 대시보드, 코스트 알림, 상태 모니터링. AHOY는 CLI 기반 출력만 제공
6. **시간 여행 디버깅**: 체크포인트로 과거 실행 상태 복원 및 분석. AHOY에는 동등한 기능 없음

### AHOY가 더 나은 점

1. **Generator-Evaluator 분리**: Hive는 동일 프레임워크 내 생성-평가. 자기평가 편향 위험 존재
2. **다중 모델 필수 컨센서스**: Hive는 단일 모델 판단. AHOY는 최소 2개 모델 합의 필수
3. **Hook 기반 하드 차단**: Hive는 소프트 가드레일. AHOY는 PreToolUse/PostToolUse로 우회 불가능한 차단
4. **파일 소유권 분리**: Hive에는 파일 수준 접근 제어 없음
5. **Generator 의견 strip**: Hive는 에이전트 출력 필터링 없음
6. **계약 기반 개발**: Hive는 자연어 목표 기반. AHOY는 contract.md로 명확한 요구사항 정의
7. **스프린트 상태머신**: Hive는 그래프 기반 자유 실행. AHOY는 엄격한 상태 전이 규칙

## 배울 만한 구체적 아이디어

### 1. 체크포인트 기반 스프린트 복구
```python
# sprint_checkpoint.py
class SprintCheckpoint:
    def save(self, sprint_id, state, context):
        """상태 전이 시마다 체크포인트 자동 저장"""
        snapshot = {
            "sprint_id": sprint_id,
            "state": state,  # planned/contracted/generated
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "files_hash": hash_project_files()
        }
        save_to_disk(f".ahoy/checkpoints/{sprint_id}/{state}.json", snapshot)

    def restore(self, sprint_id, target_state):
        """크래시 후 마지막 상태에서 복구"""
        return load_checkpoint(f".ahoy/checkpoints/{sprint_id}/{target_state}.json")
```

### 2. 자동 모델 다운그레이드 정책
```python
# eval_dispatch.py 비용 관리 추가
cost_policy = {
    "budget_limit": 5.00,  # USD per sprint
    "warning_threshold": 0.8,  # 80%에서 경고
    "degradation_chain": ["claude-opus", "claude-sonnet", "claude-haiku"],
    "auto_downgrade": True
}
```

### 3. 4단계 실행 격리
- `isolated` 모드: 각 스프린트를 독립 세션으로 실행
- `synchronized` 모드: 공유 상태 잠금으로 병렬 스프린트 간 충돌 방지

---

## AHOY 개선 제안 Top 3

### 1. 스프린트 체크포인트 및 크래시 복구 시스템
- **파일**: 신규 `sprint_checkpoint.py`, hooks 수정
- **변경**: 매 상태 전이 시 체크포인트 자동 저장 (contract.md, issues.json, 파일 해시, 컨텍스트). API 크래시/세션 종료 시 마지막 체크포인트에서 자동 복원
- **효과**: 장시간 스프린트의 안정성 대폭 향상, 비용 낭비 방지

### 2. 스프린트 토큰/비용 예산 관리 + 자동 다운그레이드
- **파일**: `eval_dispatch.py`, 신규 `.ahoy/budget.json`
- **변경**: 스프린트별 토큰/비용 하드 상한 설정. 80%에서 경고, 100%에서 강제 종료 또는 경량 모델로 자동 전환
- **효과**: runaway cost 방지, 예산 예측 가능성 확보

### 3. 실패 기반 프로세스 자동 진화 (Sprint Learning)
- **파일**: 신규 `.ahoy/evolution/`, `eval_dispatch.py` 확장
- **변경**: rework 3회 실패 시 실패 패턴(이슈 유형, 반복 카테고리)을 `.ahoy/evolution/failure_patterns.json`에 축적. 이후 스프린트에서 contract.md에 자동 경고 삽입
- **효과**: 반복 실패 패턴 학습, 스프린트 성공률 점진적 향상
