# GitHub Spec Kit 분석 리포트

> 분석일: 2026-03-28 (7차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | GitHub Spec Kit |
| URL | https://github.com/github/spec-kit |
| 스타 | ~40,600 |
| 포크 | ~3,460 |
| 최근 버전 | v0.1.4 (2026-02) |
| 라이선스 | MIT |
| 주요 키워드 | Constitution, SDD, Plan, Tasks, DAG, 멀티 에이전트 지원 |

## 핵심 아키텍처

### 1. Constitution 기반 원칙 시스템

GitHub의 공식 SDD 툴킷의 핵심은 **Constitution(헌법)** — 프로젝트의 불변 원칙:

- **9개 Article**: 스펙이 코드가 되는 방식을 통치
- **주요 원칙**: "모든 기능은 독립 라이브러리로 시작" → 모듈러 설계 강제
- 스펙 생성, 테스트, 검증의 근거가 되는 "아키텍처 DNA"

### 2. SDD 워크플로우 (5단계)

```
Constitution → Spec → Plan → Tasks → Implementation
```

1. **Constitution**: 불변 원칙 정의 (수정 불가)
2. **Spec (spec.md)**: 코드 행동 계약 — 진실의 원본
3. **Plan (plan.md)**: 구현 전략 수립
4. **Tasks**: `/speckit.tasks` 명령으로 자동 생성
   - User Story별 태스크 조직
   - 의존성 관리 (컴포넌트 간)
   - 병렬 실행 마커 (최적화)
5. **Implementation**: 태스크별 코드 생성

### 3. Specify CLI

- `specify init`: `.specify/` 디렉토리 스캐폴딩 (spec.md, plan.md, tasks/)
- `.github/` 하위에 에이전트별 프롬프트 파일 생성
- 템플릿 패키지: Copilot, Claude Code, Gemini CLI, Cursor, Windsurf 지원

### 4. Spec Kit Assistant (VS Code 확장)

- 전체 SDD 워크플로우의 시각적 오케스트레이터
- Phase 상태 시각화
- 인터랙티브 태스크 체크리스트
- **DAG 시각화**: 태스크 간 의존성 그래프
- Claude, Gemini, GitHub Copilot, OpenAI 백엔드 지원

### 5. 태스크 자동 생성 및 의존성 관리

- `/speckit.tasks`: plan.md → 구체적 태스크 자동 분해
- 의존성 분석으로 실행 순서 결정
- 병렬 실행 가능 태스크 자동 식별 및 마킹

## AHOY와 비교

### GitHub Spec Kit이 AHOY보다 나은 점

1. **Constitution (불변 원칙)**: AHOY에는 프로젝트 전체를 관통하는 불변 원칙 문서가 없음. contract.md는 스프린트별 문서
2. **DAG 기반 태스크 의존성**: 태스크 간 의존성을 그래프로 관리, 병렬 실행 가능 태스크 자동 식별. AHOY는 선형 스프린트
3. **시각적 워크플로우 도구**: VS Code 확장으로 Phase 상태, DAG, 체크리스트 시각화. AHOY는 CLI/파일 기반
4. **멀티 에이전트 템플릿**: 6+ 에이전트에 대한 프롬프트 템플릿 자동 생성. AHOY는 Claude Code 전용
5. **Plan 단계의 명시적 분리**: Spec → Plan → Tasks 3단계로 전략과 실행을 분리. AHOY의 contracted는 한 단계에 압축
6. **40k+ 스타의 커뮤니티**: GitHub 공식 프로젝트로 강력한 생태계. LinkedIn Learning 코스까지 존재

### AHOY가 GitHub Spec Kit보다 나은 점

1. **Generator-Evaluator 분리**: Spec Kit은 코드 생성자가 곧 검증자. 외부 모델 평가 메커니즘 없음
2. **다중 모델 컨센서스**: Spec Kit은 단일 에이전트 워크플로우. 평가 품질 보장 메커니즘 부재
3. **자동 평가 파이프라인**: Spec Kit의 "검증"은 수동 확인 또는 에이전트 자체 판단. AHOY는 자동화된 외부 평가
4. **하드 차단 Hook**: Spec Kit은 슬래시 커맨드 기반 (우회 가능). AHOY는 PreToolUse/PostToolUse로 구조적 차단
5. **상태머신 강제**: Spec Kit의 Phase 전이는 소프트 (에이전트 재량). AHOY는 상태 전이 규칙을 Hook으로 강제
6. **파일 소유권 분리**: Spec Kit에는 파일 쓰기 권한 분리 개념 없음
7. **Rework 안전장치**: Spec Kit은 실패 시 무한 반복 가능. AHOY는 3회 rework 제한
8. **Generator 의견 strip**: Spec Kit 에이전트의 주관적 판단이 필터링 없이 전달됨

### 배울 만한 구체적 아이디어

1. **Constitution 문서 도입**
   - 프로젝트 전체에 적용되는 불변 원칙 `constitution.md` 추가
   - contract.md가 스프린트별이라면, constitution은 프로젝트 수명 동안 유효
   - 평가 시 constitution 위반 여부도 검사
   - **적용 파일**: `.ahoy/constitution.md` 신규, `eval_dispatch.py`에 constitution 검증 로직

2. **DAG 기반 태스크 분해와 병렬 실행**
   - contract.md의 요구사항에 의존성 관계 명시
   - 독립 태스크 자동 식별 → git worktree 병렬 실행
   - **적용 파일**: contract.md 포맷에 `depends_on` 필드, 오케스트레이터에 DAG 파서

3. **Plan 단계 분리 (Spec → Plan → Tasks)**
   - `planned → contracted` 사이에 `planned → plan → contracted` 삽입
   - plan.md: 구현 전략, 아키텍처 결정, 리스크 분석
   - plan이 확정된 후에야 contract(구체적 요구사항)로 전이
   - **적용 파일**: 상태머신에 `plan` 상태 추가, Hook에 plan→contracted 전이 규칙

---

## AHOY 개선 제안 Top 3

### 1. Constitution (불변 원칙) 도입
- **현재**: 프로젝트 전체 원칙이 없고, contract.md만 스프린트별 관리
- **제안**: `.ahoy/constitution.md`로 프로젝트 수준 불변 규칙 정의
- **구현**:
  - `constitution.md`: 코딩 표준, 금지 패턴, 아키텍처 원칙, 보안 요구사항
  - `eval_dispatch.py`에서 평가 시 constitution 위반 여부 추가 검사
  - Hook에서 constitution 변경 시도 시 하드 차단
  - contract.md 작성 시 constitution 자동 참조 삽입
- **예상 효과**: 스프린트 간 일관성 유지, 반복적 평가 실패(동일 원칙 위반) 감소

### 2. DAG 기반 태스크 의존성 관리
- **현재**: 선형 스프린트로 태스크 순차 처리
- **제안**: contract.md에 태스크 의존성 그래프 명시, 병렬 실행 활성화
- **구현**:
  - contract.md 포맷에 `## Task Dependencies` 섹션 + `depends_on: [task_id]` 필드
  - DAG 파서로 병렬 실행 가능 그룹 자동 식별
  - git worktree 기반 병렬 스프린트 실행 (이전 Spec-Kitty 제안과 결합)
- **예상 효과**: 독립 태스크 N개 동시 처리, 전체 개발 시간 단축

### 3. Plan 단계 명시적 분리
- **현재**: `planned → contracted`로 바로 전이 (전략과 구체 요구사항 혼합)
- **제안**: `planned → planning → contracted` 3단계로 분리
- **구현**:
  - 상태머신에 `planning` 상태 추가
  - `plan.md`: 구현 전략, 기술 선택 근거, 리스크 분석, 대안 비교
  - Generator가 plan.md 작성 → Evaluator가 plan 검증 → 통과 시 contracted 전이
  - plan 단계 평가 기준: 실현 가능성, 스펙 커버리지, 리스크 식별 완전성
- **예상 효과**: contract 품질 향상 → rework 횟수 감소, 아키텍처 결정의 추적 가능성
