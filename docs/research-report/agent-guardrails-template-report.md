# TheArchitectit/agent-guardrails-template 분석 리포트

> 분석일: 2026-03-28 (5차)

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | agent-guardrails-template |
| URL | https://github.com/TheArchitectit/agent-guardrails-template |
| 스타 | 30 |
| 최근 버전 | v2.8.0 (2026-03-14) |
| 라이선스 | BSD-3-Clause |
| 핵심 키워드 | 4대 법칙, MCP 서버 (Go), 17 도구, 토큰 효율, 멀티 도메인 가드레일 |

## 핵심 아키텍처

### 4대 에이전트 안전 법칙 (The Four Laws)

1. **Read before editing** — 코드 수정 전 반드시 기존 코드 리뷰
2. **Stay in scope** — 명시적으로 인가된 파일만 수정
3. **Verify before committing** — 모든 변경사항 커밋 전 테스트
4. **Halt when uncertain** — 불확실할 때 추측 대신 확인 요청

### MCP 서버 (Go 1.23+)

```
MCP Server (Go)
├─ PostgreSQL 16 (상태 영속)
├─ Redis 7 (캐시/세션)
├─ SSE Stream (/mcp/v1/sse)
├─ JSON-RPC (/mcp/v1/message)
└─ Web UI (/web)
```

- **17 MCP 도구**: 세션 초기화, bash/파일/git 검증, 스코프 확인, 회귀 방지, 팀 관리
- **8 MCP 리소스**: 빠른 참조 가이드, 활성 규칙 문서, 문서 액세스 인터페이스

### 토큰 효율 도구

| 도구 | 효과 |
|------|------|
| INDEX_MAP.md | 키워드 검색으로 60-80% 토큰 절약 |
| HEADER_MAP.md | 섹션 점프 (라인 번호 포함) |
| .claudeignore | 불필요 파일 제외 |
| 500줄 제한 | 문서당 최대 500줄 강제 |

### 멀티 도메인 가드레일 (7개 카테고리)

1. Safety (일반 안전)
2. Game Design (게임 디자인)
3. Commerce (전자상거래, IAP 윤리, 루트박스 투명성)
4. Social (채팅 중재, CSAM 감지)
5. Analytics (동의 계층, 개인정보)
6. Deployment (크로스 플랫폼 컴플라이언스)
7. Generative (생성 자산 안전, C2PA 메타데이터)

### 14개 언어 지원

Go, TypeScript, Rust, Python, Java, Swift, Dart/Flutter, GDScript, Scala, R, C#, C++, PHP, Ruby

## AHOY와 비교

### AHOY보다 나은 점

1. **MCP 서버 기반 실시간 가드레일**: Go로 구현된 독립 서버가 모든 bash/파일/git 작업을 실시간 검증. AHOY의 Hook은 Claude Code 프로세스 내부에서 실행되지만, 이 프로젝트는 외부 서비스로 분리하여 독립성 확보
2. **토큰 효율 시스템**: INDEX_MAP/HEADER_MAP으로 컨텍스트 윈도우 사용량 60-80% 절감. AHOY는 handoff 문서로 컨텍스트 리셋하지만 토큰 효율 최적화 도구 부재
3. **4대 법칙의 단순성**: 기억하기 쉬운 4가지 원칙으로 모든 규칙 집약. AHOY는 상세한 상태머신 규칙이 있지만 직관적 요약 부재
4. **멀티 도메인 가드레일 템플릿**: 게임/상거래/소셜 등 다양한 도메인별 가드레일 프리셋. AHOY는 코딩 특화이지만 도메인 확장 템플릿 없음
5. **44+ 문서 생태계**: 방대한 가이드/표준 문서. 온보딩이 체계적

### AHOY가 더 나은 점

1. **Generator-Evaluator 분리**: agent-guardrails-template은 자기검증 패턴. 외부 모델 평가 없음
2. **다중 모델 컨센서스**: 단일 MCP 서버 판단에 의존. 복수 평가자 합의 메커니즘 없음
3. **상태머신 기반 스프린트 사이클**: planned→contracted→generated→passed 프로세스 없음. 개별 작업 단위 검증만 수행
4. **파일 소유권 분리**: 모든 에이전트가 동일 권한으로 파일 접근. issues.json 같은 쓰기 권한 분리 없음
5. **Generator 의견 strip**: 평가 결과에서 주관적 판단을 제거하는 메커니즘 없음

## 배울 만한 구체적 아이디어

### 1. INDEX_MAP 기반 토큰 절약 (높은 가치)

AHOY handoff 문서에 INDEX_MAP 패턴 적용:

```markdown
# AHOY_INDEX_MAP.md
## 키워드 → 파일 매핑
- contract: sprint_N/contract.md (L1-L50)
- issues: sprint_N/issues.json (전체)
- eval_config: config/eval_config.json (L1-L30)
- state: sprint_state.json (L1-L20)
```

**적용 파일**: handoff 문서 생성 로직 — `generate_handoff.py`에 INDEX_MAP 자동 생성 추가

### 2. MCP 서버 기반 독립 가드레일 서비스

eval_dispatch.py를 독립 Go/Python 서비스로 분리:

```
AHOY MCP Server
├─ /validate/state-transition  (상태 전이 검증)
├─ /validate/file-ownership    (파일 소유권 검증)
├─ /validate/scope             (스코프 검증)
└─ /eval/dispatch              (평가 디스패치)
```

**적용 방향**: NeMo Guardrails 리포트의 서버 모드 제안과 결합하여 FastAPI/Go 기반 독립 서비스 구축

### 3. 문서당 500줄 제한 규칙

contract.md, handoff 문서 등에 500줄 하드 제한 적용. 초과 시 자동 분할:

**적용 파일**: `hooks/post_tool_use.py` — 문서 파일 쓰기 후 줄 수 검사, 500줄 초과 시 경고

---

## AHOY 개선 제안 Top 3

1. **Handoff 문서에 INDEX_MAP 자동 생성** — `generate_handoff.py`에서 현재 스프린트의 핵심 파일/키워드 매핑을 INDEX_MAP으로 자동 생성. 새 세션이 전체 handoff를 읽지 않고 필요한 부분만 참조 가능. 컨텍스트 토큰 40-60% 절감 예상

2. **4대 법칙 스타일의 직관적 규칙 요약** — AHOY 상태머신 규칙을 4-5개의 기억하기 쉬운 법칙으로 요약하여 CLAUDE.md 상단에 배치. 새 세션 시작 시 복잡한 규칙 전체를 로드하기 전 핵심 원칙 즉시 적용

3. **문서 크기 하드 제한 Hook** — `hooks/post_tool_use.py`에 contract.md/handoff 문서 500줄 초과 감지 추가. 초과 시 자동 경고 또는 분할 제안. 컨텍스트 윈도우 낭비 방지
