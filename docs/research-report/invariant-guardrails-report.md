# Invariant Guardrails 분석 리포트

> 분석일: 2026-03-28 (3차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Invariant Guardrails |
| GitHub URL | https://github.com/invariantlabs-ai/invariant |
| 스타 | 401 |
| 최근 커밋 | 2025-02 (252 commits) |
| 라이선스 | Apache 2.0 |
| 언어 | Python |
| 기여자 | 9명 |
| 관련 프로젝트 | invariant-gateway (MCP/LLM 프록시) |

## 핵심 아키텍처

### 프록시 기반 비침투적 가드레일

```
AI Application
     ↓
Invariant Gateway (MCP/LLM Proxy)
     ↓                    ↓
MCP Servers          LLM Provider
```

- 애플리케이션 코드 수정 없이 배포
- base URL만 변경하면 즉시 적용
- 모든 tool call/LLM 요청을 투명하게 인터셉트

### Python-Inspired 규칙 DSL

```python
raise "violation message" if:
    (call: ToolCall) -> (output: ToolOutput)
    call is tool:send_email
    "confidential" in output.content
```

핵심 구문 요소:
- **이벤트 타입 매칭**: `ToolCall`, `ToolOutput`, `Message`
- **플로우 연산자 (`->`)**: 순차적 이벤트 체인 감지
- **패턴 매칭**: 도구 이름, 인자 값 매칭
- **정규식 지원**: 파라미터 값 패턴
- **표준 라이브러리**: `prompt_injection()` 등 내장 함수

### 2가지 배포 모드

1. **Gateway 통합**: MCP/LLM 프록시로 투명 배포
2. **프로그래밍 방식**: `LocalPolicy.from_string()` 으로 라이브러리로 사용

### 플로우 기반 탐지 (핵심 차별점)

단일 이벤트가 아닌 **다단계 이벤트 시퀀스** 탐지:

```python
raise "data exfiltration" if:
    (read: ToolCall) -> (send: ToolCall)
    read is tool:read_file
    send is tool:send_email
    read.output in send.args.body
```

## AHOY 대비 비교

### Invariant가 AHOY보다 나은 점

1. **표현력 높은 규칙 DSL**: Python-inspired 문법으로 복잡한 조건/플로우 정의 가능. AHOY hook은 개별 셸 스크립트
2. **플로우 기반 다단계 탐지**: `->` 연산자로 이벤트 시퀀스 패턴을 자연스럽게 표현. AHOY hook은 단일 이벤트만
3. **비침투적 배포**: base URL 변경만으로 기존 시스템에 적용. AHOY는 프로젝트별 hook 설정 필요
4. **MCP + LLM 이중 프록시**: MCP 서버 호출과 LLM API 호출 모두 인터셉트. AHOY는 Claude 내장 도구만
5. **로컬 완전 실행**: 외부 API 호출 없이 로컬에서 규칙 평가 (OpenGuardrails와 달리). AHOY와 동일한 장점
6. **내장 보안 함수**: `prompt_injection()` 등 사전 구현된 탐지 함수 제공

### AHOY가 Invariant보다 나은 점

1. **Generator-Evaluator 분리**: Invariant는 규칙 기반 게이팅만. 코드 품질 평가 없음
2. **다중 모델 컨센서스**: 없음
3. **스프린트 상태머신**: 없음. 개별 요청 수준 검사만
4. **계약 기반 개발**: 없음
5. **Generator 의견 strip**: 없음
6. **코드 생성 워크플로우**: 없음. 보안 레이어에 특화

### 배울 만한 구체적 아이디어

1. **플로우 기반 규칙 DSL → AHOY Hook DSL**
   - `->` 연산자 개념을 hook 규칙에 도입
   - `Read(.env) -> Bash(curl)` 같은 시퀀스 규칙을 YAML/DSL로 정의
   - 기존 제안 "선언적 Hook 규칙 DSL"의 구체적 문법 참조

2. **프록시 패턴 → eval_dispatch 미들웨어화**
   - `eval_dispatch.py`를 독립 프록시 서비스로 분리
   - 여러 프로젝트에서 공유 가능한 평가 서비스
   - 기존 제안 "평가 서비스 서버 모드"의 구체적 아키텍처 참조

3. **내장 보안 함수 라이브러리**
   - `prompt_injection()`, `pii_detection()` 등 사전 구현된 검사 함수를 hook에서 import 가능하게
   - `ahoy_stdlib/` 패키지로 표준화

---

## AHOY 개선 제안 Top 3

### 1. 플로우 기반 Hook 규칙 DSL
- **구현 대상**: hook 시스템 (새 규칙 엔진)
- **변경 내용**: Invariant의 `->` 연산자 개념을 차용. YAML 형식으로 다단계 tool call 시퀀스 규칙 정의:
  ```yaml
  rules:
    - name: "data_exfiltration"
      flow:
        - action: Read
          pattern: "*.env|*.key|*.pem"
        - action: Bash
          pattern: "curl|wget|nc"
      response: block
  ```
- **효과**: 복잡한 보안 패턴을 선언적으로 정의. 단일 이벤트 hook의 한계 극복
- **참조**: Invariant `->` 연산자, OpenGuardrails 행동 패턴 체인

### 2. Hook 표준 보안 라이브러리
- **구현 대상**: `ahoy_stdlib/` (새 패키지)
- **변경 내용**: `prompt_injection_check()`, `pii_detect()`, `credential_scan()` 등 재사용 가능한 보안 검사 함수 라이브러리. hook 스크립트에서 `from ahoy_stdlib import prompt_injection_check` 으로 사용
- **효과**: hook 개발 시 보안 검사 로직 재작성 불필요. 일관된 탐지 품질
- **참조**: Invariant 표준 라이브러리 함수

### 3. eval_dispatch 미들웨어 서비스화
- **구현 대상**: `eval_dispatch.py` → FastAPI 독립 서비스
- **변경 내용**: Invariant Gateway처럼 평가 기능을 독립 HTTP 서비스로 분리. 여러 프로젝트의 AHOY 인스턴스가 하나의 평가 서비스를 공유. 평가 설정/모델/캐시를 중앙 관리
- **효과**: 프로젝트별 eval_dispatch 설정 중복 제거. 평가 모델 관리 일원화
- **참조**: Invariant Gateway, NeMo Guardrails 서버 모드
