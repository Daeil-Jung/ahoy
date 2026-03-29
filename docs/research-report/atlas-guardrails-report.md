# Atlas Guardrails 분석 리포트

> 분석일: 2026-03-28

## 프로젝트 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Atlas Guardrails |
| URL | https://github.com/marcusgoll/atlas-guardrails |
| 스타 | 3 |
| 최근 릴리즈 | v1.0.1 (2026-01-22, Initial Release) |
| 라이선스 | MIT |
| 주요 언어 | TypeScript (88.5%), Shell (5.2%), PowerShell (5.2%) |
| 테스트 커버리지 목표 | >80% |

## 핵심 아키텍처

Atlas는 **로컬 퍼스트 MCP 서버**로, AI 코딩 에이전트가 "지도를 먼저 읽고(read the map)" 코드를 작성하도록 강제하는 가드레일. 3개 핵심 컴포넌트로 구성.

### 3대 핵심 컴포넌트

#### 1. Symbol Indexing Engine
- 레포지토리의 export/의존성을 **결정론적 그래프**로 구축
- `atlas_index` 명령으로 심볼 그래프 빌드/업데이트
- 파일 간 의존 관계 추적

#### 2. Context Packing System
- 태스크 설명을 받아 **토큰 최적화된 파일 컬렉션** 반환
- `atlas_pack(task="...")` — 관련 파일 + 의존성 트레일 제공
- 에이전트의 환각/기존 유틸리티 재발명 방지

#### 3. Guardrail Enforcement
- **Anti-Duplication**: `atlas_find_duplicates(intent="...")` — 새 유틸리티 생성 전 기존 구현 검색
- **Drift Detection**: `atlas check` — public API 변경 감지, 사일런트 브레이킹 방지

### 결정론적 워크플로우 루프

```
1. Index Terrain    → atlas_index          (심볼 그래프 빌드)
2. Pack Context     → atlas_pack(task)      (관련 파일 수집)
3. Prevent Duplication → atlas_find_duplicates (중복 검사)
4. Enforce Guardrails  → atlas check          (API 일관성 검증)
```

### 통합 방식

| 플랫폼 | 통합 방법 |
|--------|----------|
| Claude Code | CLAUDE.md + MCP 도구 자동 로드 |
| Gemini CLI | native extension 또는 수동 MCP |
| Cursor/Windsurf | config 파일 또는 IDE 설정 |
| Claude Desktop | JSON 설정 |
| Standalone | npm global install CLI |

### Instruction File 전략

프로젝트 루트의 `CLAUDE.md`/`GEMINI.md`/`AGENTS.md`에 도구 사용 의무화 규칙 삽입 → 에이전트가 인덱싱/패킹 워크플로우를 우회할 수 없도록 강제.

## AHOY와의 비교 분석

### AHOY보다 나은 점

| 영역 | Atlas 장점 | 상세 |
|------|-----------|------|
| **컨텍스트 품질 보장** | 결정론적 심볼 그래프 기반 컨텍스트 패킹 | AHOY는 Generator에게 컨텍스트 수집을 일임. Atlas는 관련 파일을 자동으로 토큰 최적화하여 제공 |
| **코드 중복 방지** | 생성 전 기존 구현 자동 검색 | AHOY는 중복 코드 생성을 사후 평가에서만 감지. Atlas는 사전에 방지 |
| **API Drift Detection** | public API 변경 자동 감지 | AHOY는 API 호환성 검증 메커니즘 없음 |
| **MCP 서버 아키텍처** | 표준 MCP 프로토콜로 다중 플랫폼 지원 | AHOY는 Claude Code Hook에 강결합 |
| **결정론적 워크플로우** | 인덱스→패킹→중복검사→가드레일 순서 강제 | AHOY의 Generator 작업 순서는 프롬프트 의존 |

### AHOY가 더 나은 점

| 영역 | AHOY 장점 | 상세 |
|------|-----------|------|
| **Generator-Evaluator 분리** | 외부 모델 평가 | Atlas는 평가 기능 없음 (가드레일만, 코드 품질 평가 미포함) |
| **다중 모델 컨센서스** | 2+ 모델 합의 | Atlas는 단일 에이전트 가드레일 도구 |
| **상태머신 기반 스프린트** | 전체 개발 라이프사이클 관리 | Atlas는 단일 태스크 수준 가드레일. 스프린트/라이프사이클 관리 없음 |
| **Hook 기반 하드 차단** | 상태 전이 규칙 강제 | Atlas의 강제는 Instruction File 기반 (소프트, 우회 가능) |
| **파일 소유권 분리** | issues.json 물리적 쓰기 분리 | Atlas는 파일 소유권 개념 없음 |
| **계약 기반 개발** | contract.md 기반 개발 | Atlas는 태스크 단위 컨텍스트 패킹만 |
| **컨텍스트 리셋** | 주기적 handoff | Atlas는 세션 관리 없음 |

### 핵심 포지셔닝 차이

Atlas는 AHOY의 **경쟁자가 아니라 보완재**. AHOY가 "개발 라이프사이클 전체"를 관리한다면, Atlas는 "Generator가 코드를 작성하기 직전" 단계를 최적화하는 도구.

## 배울 만한 구체적 아이디어

### 1. Contract 기반 컨텍스트 자동 패킹
```python
# contract.md의 요구사항으로부터 관련 파일을 자동 수집
# Generator에게 전달하는 컨텍스트를 토큰 최적화
# 구현: contract.md 파싱 → 키워드 추출 →
#        심볼 그래프 탐색 → 관련 파일 목록 생성
```

### 2. 생성 전 중복 검사 단계
```python
# generated 상태 전이 전에 자동 중복 검사
# Generator가 새 함수/클래스를 생성할 때
# 기존 코드베이스에서 유사 구현 검색
# 중복 발견 시 → rework with "기존 X를 재사용하라" 피드백
```

### 3. API Drift Detection을 평가 파이프라인에 통합
```python
# passed 전이 전에 atlas check 유사 검증
# 생성된 코드가 기존 public API를 변경했는지 자동 감지
# 의도치 않은 breaking change → fail + 구체적 diff 피드백
```

---

## AHOY 개선 제안 Top 3

### 1. Generator 컨텍스트 자동 패킹 시스템
- **출처**: Atlas의 Context Packing
- **구현 방향**: `contract.md`의 요구사항을 파싱하여 관련 소스 파일을 자동 수집. Generator에게 넘기는 컨텍스트를 토큰 예산 내로 최적화. 심볼 그래프까지는 과도할 수 있으므로, 키워드 기반 파일 검색 + import 체인 추적으로 경량 구현
- **대상 파일**: 신규 `context_packer.py`, `contract.md` 파싱 로직, Generator 호출 전 Hook

### 2. 생성 전 코드 중복 검사 (Pre-generation Duplicate Check)
- **출처**: Atlas의 Anti-Duplication
- **구현 방향**: Generator가 코드를 생성하기 전에 contract.md의 요구사항으로 기존 코드베이스 검색. 유사 함수/클래스가 이미 존재하면 Generator 프롬프트에 "기존 구현 X를 재사용/확장하라" 지시 삽입. 평가 단계에서도 불필요한 중복 생성을 fail 사유로 추가
- **대상 파일**: `eval_dispatch.py` (중복 검사 로직), Generator 프롬프트 템플릿

### 3. API Breaking Change 자동 감지
- **출처**: Atlas의 Drift Detection
- **구현 방향**: `generated → passed` 전이 시 public API (exported functions, class interfaces) 스냅샷 비교. 의도치 않은 시그니처 변경, 삭제된 export 등을 자동 감지. 감지 시 Evaluator에게 "API breaking change 확인 필요" 컨텍스트 제공
- **대상 파일**: 신규 `api_drift_checker.py`, PostToolUse Hook (generated 상태)
