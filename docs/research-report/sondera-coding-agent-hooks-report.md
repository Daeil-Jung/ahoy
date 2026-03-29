# Sondera Coding Agent Hooks 분석 리포트

> 분석일: 2026-03-28 (7차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Sondera Coding Agent Hooks |
| URL | https://github.com/sondera-ai/sondera-coding-agent-hooks |
| 관련 URL | https://docs.sondera.ai/ (Sondera Harness 문서) |
| 최근 활동 | 2026-03 (Unprompted 2026 발표) |
| 라이선스 | 미확인 |
| 주요 키워드 | Cedar Policy, Rust Hook, Reference Monitor, Cross-Agent, YARA, Information Flow Control |

## 핵심 아키텍처

### 1. Reference Monitor 패턴

Sondera는 AI 코딩 에이전트를 위한 **참조 모니터(Reference Monitor)** — OS 보안 모델을 에이전트에 적용:

- 모든 shell 명령, 파일 작업, 웹 요청을 **인터셉트**
- 데이터 유출(exfiltration) 및 파괴적 행동 차단
- **정보 흐름 제어(Information Flow Control)** 강제

### 2. Cedar Policy Language 기반 규칙 엔진

AWS의 [Cedar](https://www.cedarpolicy.com/) 정책 언어를 에이전트 가드레일에 도입:

- `policies/` 디렉토리에 `.cedar` + `.cedarschema` 파일
- 하네스 서버가 시작 시 모든 정책 파일 로드
- **선언적 정책 언어**: 비개발자도 읽을 수 있는 규칙 정의
- 정적 타입 검증: 스키마 기반으로 정책 오류 컴파일 타임 감지

### 3. Cross-Agent 통합 (4+ 에이전트)

에이전트별 어댑터 바이너리가 stdin/stdout JSON으로 통신:

| 에이전트 | 도구명 | 정규화 타입 |
|---------|--------|------------|
| Claude Code | Bash tool | ShellCommand |
| Cursor | Shell execution hook | ShellCommand |
| GitHub Copilot | Bash tool | ShellCommand |
| Gemini CLI | Bash tool | ShellCommand |

**핵심**: 에이전트별 도구 이름을 공통 타입으로 정규화 → Cedar 규칙이 모든 에이전트에 동일하게 적용

### 4. Rust Hook 바이너리

- Rust로 구현된 고성능 Hook 바이너리
- 에이전트 프레임워크와 stdin/stdout JSON으로 통신
- 에이전트별 어댑터 바이너리 → 공통 평가 로직
- 외부 의존성 없이 독립 실행 가능

### 5. YARA 시그니처 엔진

- YARA 패턴 매칭으로 악성 코드/민감 데이터 탐지
- Cedar 정책과 함께 외부 의존성 없이 동작
- 파일 콘텐츠, 명령어 인자 등에 대한 패턴 기반 탐지

### 6. OpenClaw 통합

- `openclaw` 프로젝트와의 통합 확장 (PR #8448)
- Cedar 정책 가드레일을 OpenClaw 생태계에 제공

## AHOY와 비교

### Sondera가 AHOY보다 나은 점

1. **정형화된 정책 언어 (Cedar)**: AHOY의 Hook은 Python/Bash 스크립트 기반. Sondera는 Cedar라는 검증된 정책 언어로 규칙 정의 → 정적 분석, 충돌 감지, 타입 검증 가능
2. **Cross-Agent 범용성**: 4+ 에이전트에 동일한 규칙 적용. AHOY는 Claude Code 전용
3. **Rust 기반 고성능**: Hook 실행 오버헤드 최소화. Python 기반 AHOY Hook보다 레이턴시 낮음
4. **YARA 기반 콘텐츠 스캐닝**: 파일 콘텐츠/명령어에 대한 패턴 기반 위협 탐지. AHOY는 상태 전이 규칙에 집중
5. **정보 흐름 제어**: 데이터가 어디로 흐르는지 추적하고 제어. AHOY는 파일 소유권 분리만 구현
6. **컴파일 타임 정책 검증**: Cedar 스키마로 정책 오류를 배포 전 감지. AHOY Hook은 런타임에만 검증

### AHOY가 Sondera보다 나은 점

1. **Generator-Evaluator 분리**: Sondera는 가드레일(방어)에 집중, 외부 모델 평가 개념 없음
2. **다중 모델 컨센서스**: Sondera는 정책 기반 pass/fail만. 다중 관점 평가 메커니즘 부재
3. **스프린트 상태머신**: Sondera는 상태 전이 워크플로우 개념 없음. 단순히 각 도구 호출을 검증
4. **계약 기반 개발**: contract.md 같은 Generator-Evaluator 공통 참조점 없음
5. **Generator 의견 strip**: Sondera는 보안 가드레일이므로 평가 편향 문제 자체가 범위 밖
6. **Rework 루프**: Sondera는 차단만 하고 대안을 제시하거나 반복 학습하는 메커니즘 없음

### 배울 만한 구체적 아이디어

1. **Cedar 정책 언어 기반 Hook 규칙 DSL 도입**
   - AHOY Hook 규칙을 Cedar로 재정의
   - 정적 타입 검증으로 규칙 충돌/오류 사전 감지
   - 기존 AgentSpec/NeMo 제안(선언적 DSL)의 구체적 구현체
   - **적용**: `.ahoy/policies/` 디렉토리에 `.cedar` 파일, Hook에서 Cedar 평가 엔진 호출

2. **에이전트 도구 정규화 레이어**
   - 모든 도구 호출을 공통 타입 (ShellCommand, FileWrite, WebRequest 등)으로 정규화
   - 규칙을 도구 이름이 아닌 공통 타입에 대해 작성
   - 향후 Claude Code 외 에이전트 지원 시 어댑터만 추가
   - **적용**: `hooks/normalizer.py` 모듈, 공통 타입 enum 정의

3. **YARA 기반 콘텐츠 스캐닝 Hook**
   - PostToolUse에서 생성된 코드에 YARA 패턴 매칭
   - 하드코딩된 비밀번호, SQL 인젝션 취약점, eval() 패턴 등 자동 탐지
   - 평가 전 사전 필터링으로 외부 모델 호출 비용 절감
   - **적용**: `hooks/content_scanner.py`, `.ahoy/yara_rules/` 디렉토리

---

## AHOY 개선 제안 Top 3

### 1. Cedar 정책 언어 기반 Hook 규칙 시스템
- **현재**: Hook 규칙이 Python 코드에 하드코딩 → 수정 시 코드 변경 필요, 규칙 충돌 감지 불가
- **제안**: Cedar 정책 언어를 Hook 규칙 엔진으로 도입
- **구현**:
  - `.ahoy/policies/sprint_rules.cedar`: 상태 전이 규칙
  - `.ahoy/policies/file_ownership.cedar`: 파일 소유권 규칙
  - `.ahoy/policies/security.cedar`: 보안 가드레일
  - `.ahoy/policies/schema.cedarschema`: 타입 정의
  - `hooks/cedar_engine.py`: Cedar 평가 래퍼 (cedarpy 패키지 활용)
  - 규칙 변경 시 Cedar 파일만 수정, 코드 변경 불필요
- **예상 효과**: 규칙 관리 비용 70% 감소, 정적 분석으로 규칙 충돌 사전 감지

### 2. 에이전트 도구 호출 정규화 레이어
- **현재**: Claude Code의 Bash/Write/Edit 도구명에 직접 의존
- **제안**: 공통 액션 타입으로 정규화하여 규칙의 도구 독립성 확보
- **구현**:
  - `hooks/normalizer.py`: `ActionType` enum (ShellCommand, FileWrite, FileRead, WebRequest, CodeEdit)
  - PreToolUse/PostToolUse에서 도구 호출을 ActionType으로 변환
  - 정책 규칙을 ActionType 기준으로 작성
  - 향후 다른 에이전트 지원 시 normalizer 어댑터만 추가
- **예상 효과**: 향후 에이전트 확장 비용 90% 감소, 규칙 재사용성 극대화

### 3. YARA 기반 사전 콘텐츠 스캐닝
- **현재**: 코드 품질/보안 검사를 전적으로 외부 평가 모델에 의존
- **제안**: 평가 전 YARA 패턴 매칭으로 명백한 문제 사전 필터링
- **구현**:
  - `.ahoy/yara_rules/secrets.yar`: API키, 비밀번호, 토큰 패턴
  - `.ahoy/yara_rules/security.yar`: eval(), exec(), SQL 인젝션, XSS 패턴
  - `.ahoy/yara_rules/quality.yar`: TODO/FIXME 과다, 빈 catch 블록, 미사용 import
  - `hooks/content_scanner.py`: PostToolUse에서 YARA 스캔 실행
  - YARA 위반 발견 시 → 외부 평가 없이 즉시 rework 지시 (비용 절감)
- **예상 효과**: 명백한 문제의 즉시 감지, 외부 평가 호출 20-30% 절감
