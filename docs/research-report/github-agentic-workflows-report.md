# GitHub Agentic Workflows (github/gh-aw) 분석 리포트

> 분석일: 2026-03-28 (8차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | GitHub Agentic Workflows |
| GitHub URL | https://github.com/github/gh-aw |
| 스타 | 4,200+ |
| 최근 커밋 | 2026-03-28 (매우 활발, 8,901 커밋) |
| 라이선스 | GitHub 소유 |
| 언어 | GitHub Actions + Markdown |
| 핵심 키워드 | 3계층 보안, Safe Outputs, 컴파일 타임 검증, MCP Gateway, 위협 감지 파이프라인 |

## 핵심 아키텍처

GitHub Agentic Workflows는 **자연어 마크다운으로 작성한 에이전트 워크플로우를 GitHub Actions로 실행**하는 시스템으로, 3계층 보안 모델과 Safe Outputs 패턴이 핵심이다.

### 3계층 보안 모델

**Layer 1 — Substrate-Level Trust (하드웨어/커널)**
- 하드웨어, 커널, 컨테이너 런타임 격리
- 신뢰 컴포넌트: 네트워크 방화벽, API 프록시, MCP Gateway
- 침해 시 하드웨어/하이퍼바이저 취약점 필요

**Layer 2 — Configuration-Level Trust (선언적 제약)**
- 스키마 검증으로 잘못된 구성 거부
- SHA 커밋 고정으로 공급망 공격 방지
- 컴파일 타임에 `.lock.yml` 생성하여 런타임 재해석 차단

**Layer 3 — Plan-Level Trust (단계별 권한)**
- 워크플로우를 단계로 분해, 각 단계에 최소 권한 부여
- 폭발 반경(blast radius) 제한
- 외부 부작용 명시적 선언 필수

### Safe Outputs 패턴 (핵심 혁신)

```
에이전트 실행 (read-only) → 아티팩트 버퍼링 → 위협 감지 → Safe Output Jobs (쓰기)
```

1. **에이전트는 읽기 전용으로만 실행**: 쓰기 권한 완전 제거
2. **쓰기 작업은 별도 Job으로 분리**: 최소 범위 권한만 부여 (issues:write 또는 contents:write)
3. **아티팩트를 즉시 외부화하지 않고 버퍼링**: 위협 감지 통과 후에만 쓰기 실행
4. **위협 감지 Job**: 비밀 유출, 악성 패치, 정책 위반 검사. 커스텀 스캐너(Semgrep, TruffleHog) 통합 가능

### 컴파일 타임 검증

- **스키마 검증**: 잘못된 frontmatter/설정 거부
- **표현식 허용목록**: 안전한 패턴만 동적 표현식 허용
- **액션 고정**: 모든 Actions를 불변 SHA로 해결
- **보안 스캐너**: actionlint(린팅), zizmor(권한 상승), poutine(공급망)

### MCP Tool 관리

- **서버별 필터링**: 설정에서 `allowed: [tool1, tool2]` 명시
- **MCP Gateway 필터링**: 목록에 없는 도구 무조건 차단
- **MCP 서버 컨테이너 격리**: 각 서버가 독립 컨테이너에서 실행, 상태 공유 없음

### 콘텐츠 정제

- @mention 중화, 봇 트리거 보호, XML/HTML 태그 변환
- URI 필터링 (HTTPS + 신뢰 도메인만), 제어 문자 제거
- 크기 제한 (0.5MB, 65k 라인)
- 비밀 자동 수정 (처음 3자 + 마스킹)

### 무결성 필터링

- `min-integrity` 설정: merged/approved/unapproved/none
- 공개 저장소: `approved` 자동 적용
- 작성자 신뢰도와 병합 상태 기반 콘텐츠 접근 제어

### 실행 상태머신

```
Pre-Activation → Activation → Agent → Detection → Safe Outputs → Conclusion
```

각 단계 실패 시 후속 단계 진행 차단.

## AHOY 비교 분석

### AHOY보다 나은 점

1. **Safe Outputs 패턴**: 에이전트와 쓰기 작업의 완전한 프로세스 분리. AHOY의 파일 소유권 분리보다 더 체계적. 에이전트가 읽기 전용으로 실행되고, 쓰기는 별도 Job이 담당
2. **3계층 보안 아키텍처**: 하드웨어→설정→계획 단계별 방어. AHOY는 Hook 레벨 방어만 존재
3. **컴파일 타임 검증**: 런타임 전에 보안 문제를 정적 분석으로 차단. AHOY는 런타임 Hook만 사용
4. **위협 감지 파이프라인**: 에이전트 출력에 대한 독립적 보안 분석 Job. AHOY는 평가자가 보안도 함께 평가
5. **MCP 서버 컨테이너 격리**: 각 MCP 서버를 독립 컨테이너로 격리. 메모리/상태 공유 완전 차단
6. **콘텐츠 정제 시스템**: @mention, 봇 트리거, 비밀 유출 등 다양한 벡터 자동 정제
7. **무결성 필터링**: 작성자 신뢰도 기반 콘텐츠 접근 제어. AHOY에는 없는 개념
8. **커뮤니티 규모**: GitHub 공식 프로젝트, 4.2k 스타, 활발한 개발

### AHOY가 더 나은 점

1. **다중 모델 컨센서스 평가**: gh-aw는 코드 품질 평가/컨센서스 메커니즘 부재. 에이전트가 생성하면 위협 감지만 수행
2. **Generator-Evaluator 분리**: gh-aw는 에이전트가 생성과 자체 판단을 동시에 수행
3. **스프린트 상태머신**: gh-aw의 실행 파이프라인은 단일 패스. 반복 개선(rework) 사이클 없음
4. **계약 기반 개발**: contract.md 같은 명시적 요구사항 문서와 평가 기준 공유 메커니즘 없음
5. **Generator 의견 strip**: 에이전트 출력에서 주관적 판단 제거하는 메커니즘 없음
6. **Hook 기반 상태 전이 강제**: gh-aw는 Job 의존성으로 순서를 강제하지만 상태 전이 규칙은 없음

### 배울 만한 구체적 아이디어

1. **Safe Outputs 패턴 (Generator 쓰기 분리)**: Generator를 완전 읽기 전용으로 실행, 코드 적용은 별도 프로세스
   - 구현: Generator Hook에서 직접 write 차단 → 생성 코드를 버퍼에 저장 → 평가 통과 후 별도 apply 프로세스가 적용
2. **컴파일 타임 사전 검증**: contract.md와 Hook 규칙을 스프린트 시작 전 정적 분석
   - 구현: `ahoy validate` 명령어로 contract.md 완전성, Hook 규칙 충돌, 파일 경로 유효성 사전 검증
3. **위협 감지 독립 파이프라인**: 평가자 외에 별도 보안 전용 검사 단계
   - 구현: generated→passed 전이 전 `ahoy security-scan` 단계 삽입 (Semgrep/TruffleHog 통합)
4. **비밀 자동 수정**: 외부 평가 모델에 코드 전송 전 비밀 마스킹
   - 구현: eval_dispatch.py에서 코드 전송 전 정규식 기반 비밀 감지/마스킹
5. **MCP Tool 허용목록**: contract.md에 사용 가능한 도구 목록 명시, Hook에서 강제
   - 구현: contract.md에 `allowed_tools:` 섹션 추가, PreToolUse Hook에서 검증

## AHOY 개선 제안 Top 3

### 1. Safe Outputs 패턴 도입 (Generator 읽기 전용 실행)
- **현재**: Generator(Claude)가 직접 파일 쓰기 수행
- **개선**: Generator를 완전 읽기 전용 모드로 실행. 생성 코드는 `.ahoy/staged/` 버퍼에 저장. 평가 통과 후 별도 apply 프로세스가 실제 파일 시스템에 적용
- **파일**: PreToolUse Hook (write 차단 → 버퍼 리다이렉트), 신규 `ahoy apply` 명령
- **효과**: Generator의 의도치 않은 파일 수정 완전 차단, 평가 전 코드 변경 사전 검토 가능

### 2. 컴파일 타임 사전 검증 (ahoy validate)
- **현재**: 스프린트 실행 중 문제 발견
- **개선**: `ahoy validate` 명령으로 스프린트 시작 전 사전 검증. contract.md 완전성, Hook 규칙 충돌, 파일 경로 유효성, 평가 모델 가용성 확인
- **파일**: 신규 `ahoy_validate.py` (정적 분석기), `.ahoy/validation_rules.yaml`
- **효과**: 런타임 오류 50% 이상 사전 차단, rework 횟수 감소

### 3. 위협 감지 독립 파이프라인
- **현재**: 보안 검사가 평가자의 코드 리뷰에 포함
- **개선**: generated 상태에서 평가 전 독립 보안 스캔 단계 삽입. Semgrep(정적 분석), TruffleHog(비밀 탐지), 커스텀 YARA 규칙 순차 실행. 보안 스캔 실패 시 평가 없이 즉시 rework
- **파일**: 신규 `security_scan.py`, `.ahoy/security_rules/`, generated→evaluating 전이에 스캔 게이트 추가
- **효과**: 명백한 보안 문제의 외부 평가 호출 차단 (비용 절감), 보안 전문성 분리
