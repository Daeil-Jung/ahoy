# damienlaine/agentic-sprint 분석 리포트

> 분석일: 2026-03-28 (5차)

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | agentic-sprint |
| URL | https://github.com/damienlaine/agentic-sprint |
| 스타 | 16 |
| 커밋 수 | 6 |
| 라이선스 | MIT |
| 핵심 키워드 | spec-driven 상태머신, 수렴 루프, 에이전트 전문화, api-contract.md, Second Brain |

## 핵심 아키텍처

### 스프린트 상태머신

```
/sprint 커맨드 실행
    ↓
[Phase 1: Specification Analysis]
  └─ Project Architect가 specs.md 분석 → 기술 스펙 생성
    ↓
[Phase 2: Parallel Implementation]
  ├─ python-dev (FastAPI/PostgreSQL)
  ├─ nextjs-dev (Next.js 16/React 19)
  ├─ cicd-agent (GitHub Actions/Docker)
  ├─ allpurpose-agent (범용)
  └─ website-designer (HTML/CSS)
    ↓
[Phase 3: Testing & Validation]
  ├─ qa-test-agent (pytest/jest/vitest)
  ├─ ui-test-agent (Chrome MCP E2E)
  └─ nextjs-diagnostics-agent (런타임 모니터링)
    ↓
[Phase 4: Review & Iteration]
  └─ Architect가 스펙 대비 결과 평가 → 수렴/발산 판단
    ↓
[Phase 5: Completion] 또는 → Phase 2 반복 (최대 5회)
```

### 수렴 메커니즘 (Diffusion Process)

agentic-sprint의 가장 독창적인 개념:

1. **컨텍스트 축소 (Context Shrinkage)**: 완료된 작업을 활성 스펙에서 제거. 반복할수록 처리 범위가 줄어듬
2. **시그널 개선 (Signal Improvement)**: 작동하는 코드는 그대로 유지, 문제 영역만 재작업
3. **노이즈 감소 (Noise Reduction)**: 각 패스가 미완료 항목에만 집중

대부분 5회 반복 내 수렴. 수렴 실패 시 시스템 일시정지 → 사람에게 3가지 선택:
- 스펙 조정
- 추가 반복 허용
- 수동 개입

### api-contract.md 시스템

- Architect가 자동 생성하는 에이전트 간 공유 인터페이스 문서
- request/response 구조와 통합 포인트 정의
- **모든 에이전트가 이 계약을 참조**하여 구현

### Second Brain (지식 영속 시스템)

| 파일 | 관리자 | 내용 |
|------|--------|------|
| project-goals.md | 사용자 | 비즈니스 비전, 시장 포지셔닝, 성공 메트릭 |
| project-map.md | Architect | 기술 아키텍처, API 표면, DB 스키마, 컴포넌트 위치 |

멀티 스프린트 간 컨텍스트 유지, 토큰 사용량 감소.

## AHOY와 비교

### AHOY보다 나은 점

1. **수렴 메커니즘 (Diffusion Process)**: AHOY의 rework는 전체 재평가. agentic-sprint는 완료된 부분을 제거하여 반복할수록 범위가 자동 축소. 더 효율적인 수렴
2. **전문화된 에이전트 풀**: 기술 스택별 전문 에이전트 (python-dev, nextjs-dev 등). AHOY는 Claude 단일 Generator에 의존
3. **Second Brain 지식 영속**: project-goals.md + project-map.md로 스프린트 간 비즈니스/기술 컨텍스트 유지. AHOY의 handoff는 기술 상태만 전달, 비즈니스 맥락 손실 가능
4. **E2E 테스트 에이전트 (Chrome MCP)**: UI 수준 자동 테스트. AHOY는 코드 수준 평가만 수행, 실제 실행 검증 없음
5. **스펙 기반 자동 수렴 판정**: Architect가 스펙 대비 자동으로 수렴/발산 판단. AHOY는 외부 평가자 pass/fail 기반이지만 "어느 정도 완료되었는지"의 정량적 수렴 지표 없음

### AHOY가 더 나은 점

1. **Generator-Evaluator 구조적 분리**: agentic-sprint의 Architect는 스펙 생성도 하고 평가도 함 → 자기평가 편향 위험. AHOY는 Claude(생성)와 Codex/Gemini(평가)가 완전 분리
2. **다중 모델 필수 컨센서스**: agentic-sprint은 Architect 단독 판단. AHOY는 최소 2개 외부 모델 합의 필수
3. **Hook 기반 하드 차단**: agentic-sprint은 에이전트 자율에 의존. AHOY의 Hook은 상태 전이를 런타임에서 강제
4. **파일 소유권 분리**: agentic-sprint의 모든 에이전트가 모든 파일 접근 가능. AHOY의 issues.json 쓰기 권한 분리가 더 엄격
5. **Generator 의견 strip**: agentic-sprint의 Architect 평가에 주관적 판단 포함 가능. AHOY는 gen_report에서 사실만 추출
6. **rework 하드 리밋**: agentic-sprint은 5회이지만 강제성 약함 (사람이 추가 허용 가능). AHOY는 3회 하드 리밋

## 배울 만한 구체적 아이디어

### 1. 수렴 메커니즘 (Context Shrinkage) 도입 (최고 우선순위)

rework 시 passed된 항목을 contract.md에서 제거하여 다음 평가 범위 자동 축소:

```python
def shrink_contract(contract, passed_items):
    """passed된 요구사항을 contract에서 제거"""
    remaining = [item for item in contract.requirements
                 if item.id not in passed_items]
    return Contract(requirements=remaining)
```

**적용 파일**: `sprint_state_machine.py` — rework 전이 시 contract 축소 로직 추가

### 2. Second Brain 패턴으로 Handoff 확장

현재 handoff 문서에 비즈니스 맥락(project-goals.md)과 기술 맵(project-map.md) 추가:

```
sprint_memory/
├─ handoff_sprint_N.md     (기존: 기술 상태)
├─ project_goals.md        (신규: 비즈니스 목표, 변경 불가)
└─ project_map.md          (신규: 아키텍처 맵, Architect 자동 업데이트)
```

**적용 파일**: `generate_handoff.py` — project_map.md 자동 생성 로직 추가

### 3. 수렴도 정량화 지표

> **v0.2.0 구현 완료** — `eval_dispatch.py:_merge_criteria_results()` convergence_ratio 산출 + `_record_convergence()`로 harness_state.json 추적

스프린트별 수렴 진행도를 수치로 추적:

```python
convergence_ratio = passed_requirements / total_requirements
# 0.0 = 전혀 수렴 안 됨, 1.0 = 완전 수렴
```

**적용 파일**: `eval_dispatch.py` — 평가 후 수렴도 자동 계산, issues.json에 포함

---

## AHOY 개선 제안 Top 3

1. **수렴 메커니즘 (Context Shrinkage) 도입** — `sprint_state_machine.py`에서 rework 진입 시 이전 라운드에서 passed된 요구사항을 contract.md에서 자동 제거. 반복할수록 평가 범위와 토큰 소비가 줄어들어 rework 효율 대폭 향상. 구현 비용 중간 (contract 파싱 + 부분 업데이트 로직)

2. **수렴도 정량화 지표 추가** — `eval_dispatch.py`에서 `passed_requirements / total_requirements` 비율을 매 평가 후 계산하여 issues.json에 `convergence_ratio` 필드 추가. 0→1로 수렴 추적, 3회 rework 내 수렴 실패 시 원인 분석 용이

3. **Second Brain 패턴 (project_map.md)** — `generate_handoff.py`에 아키텍처 맵 자동 생성 추가. 파일 구조/API 엔드포인트/DB 스키마를 자동 추출하여 영속 문서로 유지. 3 스프린트마다 컨텍스트 리셋 시 비즈니스/기술 맥락 보존
