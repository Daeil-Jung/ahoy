# Oh-My-OpenAgent (OmO) 분석 리포트

> 분석일: 2026-03-27

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Oh-My-OpenAgent (OmO) |
| URL | https://github.com/code-yeongyu/oh-my-openagent |
| 스타 | 44.1k |
| 포크 | 3.3k |
| 라이선스 | SUL-1.0 |
| 최근 활동 | 활발 (214 open issues, 154 open PRs) |

## 핵심 아키텍처

### 멀티 에이전트 오케스트레이션
특화된 페르소나가 태스크 유형별로 작업을 분담하는 구조:

| 에이전트 | 모델 | 역할 |
|----------|------|------|
| Sisyphus | Claude Opus 4.6 / Kimi K2.5 | 메인 오케스트레이터, 전체 진행 관리 |
| Hephaestus | GPT-5.4 | 자율적 딥 워크, E2E 실행 |
| Prometheus | Claude Opus 4.6 / Kimi K2.5 | 전략 기획, 인터뷰 모드 계획 수립 |
| Oracle | 가변 | 아키텍처 결정, 디버깅 |
| Librarian | 가변 | 문서화, 코드 검색 |
| Explore | 가변 | 빠른 코드베이스 grep |
| Multimodal Looker | 비전 모델 | 이미지/시각 분석 |

### 작업 분류 시스템
- `visual-engineering`: 프론트엔드, UI/UX
- `deep`: 자율 리서치 + 실행
- `quick`: 단일 파일 변경
- `ultrabrain`: 어려운 로직, 아키텍처 (GPT-5.4 xhigh 라우팅)

### Hash-Anchored Edit Tool
에이전트가 읽는 모든 라인에 content hash 태그(`LINE#ID`)가 부여되어 파일 상태 검증 후 수정 적용. Stale-line 에러 근본 해결.

### 컨텍스트 관리
- `/init-deep`으로 프로젝트/디렉토리/컴포넌트 단위 AGENTS.md 계층 생성
- 스킬 내장 MCP 서버 (온디맨드 활성화)
- 백그라운드 에이전트 병렬 실행 (동시성 제한 설정 가능)

## AHOY와 비교

### AHOY보다 나은 점
1. **모델 라우팅 자동화**: 태스크 유형별 최적 모델 자동 선택. AHOY는 Generator(Claude) + Evaluator(Codex/Gemini) 고정 구조
2. **Hash-Anchored Edit**: 파일 수정 시 content hash로 무결성 검증. AHOY에는 이 수준의 파일 무결성 검증 없음
3. **에이전트 병렬 실행**: 다수 전문 에이전트가 동시 작업. AHOY는 단일 Generator 순차 실행
4. **자동 세션 복구**: API 실패, 컨텍스트 한도 초과 시 자동 복구. AHOY는 수동 rework 사이클
5. **Ralph Loop**: 100% 완료까지 자기참조 실행 루프

### AHOY가 더 나은 점
1. **Generator-Evaluator 분리 원칙**: OmO는 같은 모델이 생성+평가를 겸할 수 있어 자기평가 편향 위험 존재. AHOY는 구조적으로 차단
2. **다중 모델 컨센서스 평가**: OmO는 평가 전용 컨센서스가 없음. 오케스트레이터가 결과를 판단하지만 독립 평가자 합의는 없음
3. **스프린트 상태머신**: OmO는 자유도 높은 실행 방식이지만 상태 전이 규칙이 강제되지 않음. AHOY는 planned→contracted→generated→passed 엄격 관리
4. **파일 소유권 분리**: OmO는 모든 에이전트가 파일 접근 가능. AHOY는 issues.json 등 소유권 강제 분리
5. **Generator 의견 strip**: OmO에서 에이전트 주관적 판단 필터링 메커니즘 없음
6. **계약 기반 개발**: contract.md 같은 Generator-Evaluator 공통 참조점 없음

### 배울 만한 구체적 아이디어
1. **Hash-Anchored Edit 패턴**: 파일 읽기 시 라인별 해시를 부여하고 수정 시 해시 일치 검증 → AHOY의 hook에서 파일 수정 전 무결성 체크로 적용 가능
2. **작업 분류 기반 모델 라우팅**: eval_dispatch.py에서 평가 난이도별로 다른 모델 할당 (단순 린트 → 가벼운 모델, 아키텍처 리뷰 → 강력한 모델)
3. **Todo Enforcer 패턴**: idle 에이전트를 작업으로 끌어오는 메커니즘 → rework 루프에서 Generator가 멈출 때 자동 재시작에 활용

---

## AHOY 개선 제안 Top 3

### 1. Hash-Anchored File Integrity Check 도입
**현재 문제**: AHOY Hook이 파일 소유권은 검증하지만 파일 내용 무결성(stale read)은 검증하지 않음
**구현 방향**:
- `hooks/pre_tool_use.py`에 파일 읽기 시 라인별 content hash 캐시 추가
- `hooks/post_tool_use.py`에서 Write/Edit 작업 전 해시 비교 로직 추가
- 해시 불일치 시 Generator에게 파일 재읽기 강제

### 2. 평가 난이도 기반 모델 라우팅
**현재 문제**: eval_dispatch.py가 모든 평가를 동일 모델 조합으로 처리
**구현 방향**:
- `eval_dispatch.py`에 태스크 복잡도 분류기 추가 (lint/test → lightweight, architecture/security → heavyweight)
- `config.json`에 모델 티어 설정 (tier1: fast+cheap, tier2: standard, tier3: deep analysis)
- 비용 최적화와 평가 품질 균형 달성

### 3. 자동 세션 복구 메커니즘
**현재 문제**: API 실패나 컨텍스트 한도 초과 시 수동 개입 필요
**구현 방향**:
- `eval_dispatch.py`에 API 호출 재시도 로직 추가 (exponential backoff)
- handoff 문서 자동 생성 트리거를 3 스프린트 고정이 아닌 컨텍스트 사용률 기반으로 변경
- `sprint_state.json`에 복구 체크포인트 필드 추가
