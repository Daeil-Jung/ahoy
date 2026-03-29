# AgentSpec 분석 리포트

> 분석일: 2026-03-27

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | AgentSpec |
| URL | https://arxiv.org/abs/2503.18666 |
| 유형 | 학술 논문 (ICSE 2026) |
| 도메인 | 코드 실행, 임베디드 에이전트, 자율 주행 |
| 최근 활동 | 2025-2026 논문 발표 |

## 핵심 아키텍처

### 도메인 특화 언어 (DSL)
에이전트 런타임 제약 사항을 명세하고 강제하기 위한 경량 DSL. 규칙 구성:
- **Trigger**: 트리거 이벤트 (예: 금융 거래 실행)
- **Predicate**: 조건 (예: 거래 금액 > 임계값)
- **Enforcement**: 강제 메커니즘 (예: 사용자 확인 요구)

### 강제 메커니즘
- **Action Termination**: 위반 행동 즉시 중단
- **User Inspection**: 사용자에게 확인 요청
- **Corrective Invocation**: 수정 행동 자동 호출
- **Self-Reflection**: 에이전트에게 자체 검토 요구

### 통합 방식
LangChain 등 LLM 에이전트 플랫폼에 통합. 주요 실행 단계를 인터셉트하여 사용자 정의 제약 강제.

### 성과
- 코드 에이전트: 90%+ 위험 실행 방지
- 임베디드 에이전트: 100% 위험 행동 제거
- 자율 주행: 100% 규정 준수
- 오버헤드: 밀리초 수준

## AHOY와 비교

### AHOY보다 나은 점
1. **형식적 DSL**: 선언적 언어로 제약 정의. AHOY Hook은 Python 코드로 구현 → AgentSpec이 더 선언적이고 검증 가능
2. **다중 강제 메커니즘**: Termination/Inspection/Correction/Reflection 4가지 대응. AHOY Hook은 주로 차단만
3. **도메인 불가지론**: 코딩뿐 아니라 임베디드, 자율주행 등 범용. AHOY는 코딩 전용
4. **밀리초 수준 오버헤드**: 검증 비용이 극히 낮음
5. **형식 검증 가능성**: DSL 기반이라 규칙 충돌 감지, 완전성 검증 가능

### AHOY가 더 나은 점
1. **코딩 도메인 최적화**: AHOY Hook이 코드 생성/평가 워크플로우에 특화
2. **Generator-Evaluator 분리**: AgentSpec에는 생성자/평가자 구분 없음
3. **다중 모델 컨센서스**: 없음. 단일 에이전트 제약에 집중
4. **스프린트 상태머신**: 없음. 실시간 행동 제약만
5. **파일 소유권 분리**: 없음
6. **계약 기반 개발**: 없음

### 배울 만한 구체적 아이디어
1. **선언적 규칙 DSL**: Hook 규칙을 Python 코드가 아닌 선언적 설정 파일로 정의 → 비개발자도 규칙 수정 가능
2. **Corrective Invocation**: 차단뿐 아니라 자동 수정 행동 트리거 → 파일 소유권 위반 시 올바른 경로로 자동 리다이렉트
3. **규칙 충돌 감지**: Hook 규칙 간 충돌을 사전 감지하는 정적 분석
4. **Self-Reflection 강제**: Generator에게 코드 수정 전 자체 검토를 강제하되, 최종 판단은 외부 Evaluator가

---

## AHOY 개선 제안 Top 3

### 1. 선언적 Hook 규칙 정의 시스템
**현재 문제**: Hook 규칙이 Python 코드로 하드코딩되어 수정/추가 시 코드 변경 필요
**구현 방향**:
- `rules/` 디렉토리 신규 생성
- `rules/hook_rules.yaml` 파일에 선언적 규칙 정의:
```yaml
rules:
  - name: file_ownership_check
    trigger: pre_tool_use
    event: file_write
    predicate: "target_file == 'issues.json'"
    enforcement: terminate
    message: "issues.json은 eval_dispatch.py만 작성 가능"
  - name: sprint_state_check
    trigger: pre_tool_use
    event: code_generate
    predicate: "sprint_state != 'contracted'"
    enforcement: terminate
    message: "contracted 상태에서만 코드 생성 가능"
```
- `hooks/rule_engine.py`: YAML 규칙을 파싱하여 Hook 로직으로 변환
- 기존 Python Hook은 복잡한 로직용으로 유지, 단순 규칙은 YAML로 이전

### 2. 다중 강제 메커니즘 확장
**현재 문제**: Hook이 차단(terminate)만 지원하여 유연성 부족
**구현 방향**:
- `hooks/enforcement.py` 신규 생성:
  - `terminate`: 기존 하드 차단 (유지)
  - `redirect`: 잘못된 경로 접근 시 올바른 경로로 자동 변환
  - `warn_and_log`: 경고 로그 기록 후 계속 진행 (minor 위반용)
  - `require_confirmation`: 특정 행동 전 평가자 추가 확인 요구
- `rules/hook_rules.yaml`에서 규칙별 enforcement 타입 지정

### 3. Hook 규칙 충돌 사전 감지
**현재 문제**: 새 Hook 추가 시 기존 Hook과 충돌 가능성을 수동으로 확인해야 함
**구현 방향**:
- `tools/rule_validator.py` 신규 생성
- YAML 규칙 파일을 정적 분석하여 충돌 감지:
  - 동일 trigger+event에 상반되는 enforcement (terminate vs allow)
  - predicate 범위 겹침
  - 순환 의존성
- `eval_dispatch.py` 시작 시 자동 규칙 검증 실행
- 충돌 발견 시 구체적 해결 제안 출력
