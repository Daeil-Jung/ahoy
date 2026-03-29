# OpenSpec (Fission-AI) 분석 리포트

> 분석일: 2026-03-28 (7차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | OpenSpec |
| URL | https://github.com/Fission-AI/OpenSpec |
| 스타 | ~33,000 |
| 최근 커밋 | 2026-03 (활발, multi-agent orchestration PR 등) |
| 라이선스 | 미확인 |
| 주요 키워드 | SDD, Artifact-Guided Workflow, Delta Spec, 21+ AI 도구, Slash Commands |

## 핵심 아키텍처

### 1. Spec-Driven Development (SDD) 프레임워크

OpenSpec은 AI 코딩 어시스턴트를 위한 **경량 스펙 레이어**로, 코드 작성 전에 "무엇을 만들 것인지" 합의하는 구조:

- **specs/**: 시스템 행동의 진실 원본 (Source of Truth)
- **changes/**: 제안된 변경사항 (변경당 1폴더)
- **Delta Specs**: `## ADDED Requirements`, `## MODIFIED Requirements` 마커로 기존 스펙 대비 변경분 명시

### 2. Artifact-Guided Workflow (OPSX)

`/opsx:propose` 명령으로 시작되는 유동적 워크플로우:

```
proposal.md (왜 변경하는지)
→ specs/ (요구사항 + 시나리오)
→ design.md (기술적 접근)
→ tasks.md (구현 체크리스트)
→ implement → archive
```

**핵심 차이점**: 엄격한 Phase Gate 없이 어떤 아티팩트든 언제든 업데이트 가능 (유동적).

### 3. Archive 시스템

- 완료된 변경의 전체 컨텍스트 보존: proposal(왜) + design(어떻게) + tasks(무엇을 했는지)
- Delta Specs를 요구사항 수준에서 파싱하여 기존 specs에 자동 병합
- 스펙이 변경 아카이브를 통해 유기적으로 성장

### 4. 21+ AI 도구 지원

- 2계층 통합 아키텍처: **Skills** (범용 크로스-도구 포맷) + **Commands** (도구별 호출 메커니즘)
- CommandAdapterRegistry로 23개 도구별 어댑터 관리
- 지원: Claude Code, Cursor, Windsurf, Gemini CLI, GitHub Copilot, Amazon Q, Cline, RooCode 등

### 5. Multi-Agent Orchestration (진행 중)

- PR #790: `dispec-driven schema` 기반 멀티 에이전트 오케스트레이션 워크플로우
- 핵심 과제: 여러 에이전트가 병렬로 다른 태스크 그룹 작업 시 결정론적 동기화

## AHOY와 비교

### OpenSpec이 AHOY보다 나은 점

1. **Delta Spec 기반 점진적 스펙 진화**: AHOY의 contract.md는 전체 교체 방식이지만, OpenSpec은 변경분만 명시하고 archive 시 자동 병합. 스펙이 유기적으로 성장
2. **아티팩트 기반 컨텍스트 보존**: proposal(왜) + design(어떻게) + tasks(무엇)을 구조적으로 보존. AHOY의 handoff는 단순 텍스트 인계
3. **21+ AI 도구 범용 지원**: CommandAdapterRegistry로 도구 독립적. AHOY는 Claude Code 전용
4. **Archive에 의한 학습 축적**: 과거 변경의 전체 이력이 검색 가능한 형태로 축적. AHOY의 sprint_memory는 별도 구현 필요
5. **유동적 워크플로우**: Phase Gate 없이 어떤 아티팩트든 수정 가능. 탐색적 개발에 유리

### AHOY가 OpenSpec보다 나은 점

1. **Generator-Evaluator 분리**: OpenSpec은 외부 평가 모델 개념 없음. AI가 스펙 작성과 코드 생성을 모두 수행 → 자기평가 편향 미차단
2. **다중 모델 컨센서스**: OpenSpec은 단일 에이전트 실행. 멀티 에이전트 기능은 아직 PR 단계
3. **하드 차단 Hook**: OpenSpec은 slash command/skill 기반이라 Agent가 워크플로우를 우회할 가능성 존재. AHOY는 PreToolUse/PostToolUse로 구조적으로 불가능
4. **파일 소유권 분리**: OpenSpec은 모든 파일을 동일 에이전트가 읽기/쓰기. AHOY의 issues.json 쓰기 금지 같은 메커니즘 없음
5. **계약 기반 평가**: OpenSpec의 스펙은 "합의" 목적이지만 자동 평가 기준으로 사용되지 않음. AHOY의 contract.md는 평가의 참조점
6. **Rework 제한**: OpenSpec은 반복 횟수 제한 없음. AHOY는 3회 rework 후 강제 종료

### 배울 만한 구체적 아이디어

1. **Delta Spec 패턴을 contract.md에 도입**
   - `contract.md`에 `## MODIFIED` / `## ADDED` 섹션 도입
   - rework 시 전체 contract 재작성 대신 변경분만 업데이트
   - 평가 시 변경분에 집중하여 효율성 향상
   - **적용 파일**: `contract.md` 포맷 규칙, `eval_dispatch.py`의 평가 범위 로직

2. **Archive 기반 스프린트 이력 보존**
   - passed 스프린트 완료 시 `sprint_archive/` 디렉토리에 contract + 평가 결과 + 코드 변경 요약 자동 저장
   - 새 스프린트 계약 시 유사한 과거 스프린트 자동 검색
   - **적용 파일**: PostToolUse hook에 archive 트리거, `sprint_archive/` 디렉토리 구조

3. **CommandAdapter 패턴으로 평가자 인터페이스 표준화**
   - `evaluators/` 디렉토리에 Codex/Gemini/DeepSeek 등 어댑터 패턴 적용
   - 공통 인터페이스(evaluate, parse_result, normalize_findings) 정의
   - 새 평가 모델 추가 시 어댑터만 구현
   - **적용 파일**: `eval_dispatch.py` 리팩토링, `evaluators/base.py` + `evaluators/codex.py` 등

---

## AHOY 개선 제안 Top 3

### 1. Delta Contract 패턴 도입
- **현재**: contract.md는 전체 문서로 관리, rework 시 전체 재평가
- **제안**: `## MODIFIED Requirements` / `## ADDED Requirements` 마커 도입
- **구현**:
  - `contract.md` 포맷에 delta 섹션 규칙 추가
  - `eval_dispatch.py`에서 delta 섹션 파싱 → rework 시 변경 요구사항만 재평가
  - 비용 절감 + 평가 정밀도 향상
- **예상 효과**: rework 평가 토큰 30-50% 절감

### 2. Sprint Archive 시스템
- **현재**: handoff 문서만으로 세션 간 지식 전달
- **제안**: passed 스프린트마다 구조화된 아카이브 자동 생성
- **구현**:
  - `sprint_archive/{sprint_id}/` 디렉토리에 contract.md + issues.json + code_diff.patch + evaluation_summary.json 저장
  - PostToolUse hook에서 `passed` 전이 시 자동 트리거
  - 새 contract 작성 시 `sprint_archive/` 검색으로 유사 사례 참조
- **예상 효과**: 반복 실패 패턴 50% 감소, handoff 품질 향상

### 3. Evaluator Adapter 패턴 적용
- **현재**: `eval_dispatch.py`에 Codex/Gemini 호출 로직이 하드코딩
- **제안**: CommandAdapterRegistry 패턴을 차용하여 평가자 플러그인화
- **구현**:
  - `evaluators/base.py`: `BaseEvaluator(evaluate, parse, normalize)` 인터페이스
  - `evaluators/codex.py`, `evaluators/gemini.py`: 구체 구현
  - `eval_config.json`: 활성 평가자 + 가중치 + 모델 파라미터
  - `eval_dispatch.py`: 레지스트리에서 활성 평가자 로드 후 실행
- **예상 효과**: 새 평가 모델 추가 시간 80% 단축, 테스트 용이성 향상
