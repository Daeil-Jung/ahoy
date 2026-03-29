# Qodo PR-Agent 분석 리포트

> 분석일: 2026-03-28

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **프로젝트명** | Qodo PR-Agent |
| **GitHub URL** | https://github.com/qodo-ai/pr-agent |
| **스타** | ~10.7k |
| **최근 활동** | 활발 (4,891+ 커밋, 지속 업데이트 중) |
| **언어** | Python 99.9% |
| **라이선스** | Apache 2.0 |

## 핵심 아키텍처

### 명령 기반 PR 분석 시스템

PR-Agent는 PR(Pull Request)에 특화된 AI 코드 리뷰 에이전트로, 슬래시 명령어 체계를 통해 동작한다:

- **`/review`** — 종합 코드 리뷰 (보안, 테스트, 복잡도 등)
- **`/improve`** — 코드 개선 제안
- **`/describe`** — PR 요약 자동 생성
- **`/ask`** — 자연어 질의응답
- **`/update_changelog`** — 변경 로그 자동 업데이트

### 단일 LLM 호출 아키텍처

각 도구(`/review`, `/improve`, `/ask`)는 **단일 LLM 호출**로 동작 (~30초, 저비용). 이는 AHOY의 다중 모델 컨센서스와 근본적으로 다른 설계 철학이다.

### 적응형 토큰 관리

PR 크기에 따라 자동으로 컨텍스트를 압축하는 **PR Compression Strategy**를 사용. 대형 PR도 단일 호출로 처리 가능하도록 패치 피팅(adaptive token-aware file patch fitting)을 수행한다.

### 리뷰 평가 구조

리뷰는 다음 카테고리로 구성:

1. **Code Feedback** — 로직/품질 평가, 기본 최대 3개 findings
2. **Security Analysis** — 보안 취약점 탐지
3. **Testing Coverage** — 테스트 포함 여부 확인
4. **Effort Estimation** — 리뷰 난이도 1-5점 스케일
5. **PR Decomposition** — 다중 주제 PR 분할 제안
6. **Ticket Compliance** — GitHub/Jira 이슈와의 준수도 검증

### 자동 라벨링 시스템

리뷰 결과를 PR 라벨로 자동 생성:
- `possible security issue`
- `review effort [x/5]`
- `ticket compliance [level]`

## AHOY와 비교 분석

### AHOY보다 나은 점

1. **즉시 사용 가능한 CI/CD 통합** — GitHub Actions, GitLab CI, Bitbucket, Azure DevOps와 네이티브 통합. AHOY는 현재 로컬 실행 중심
2. **JSON 기반 프롬프트 커스터마이제이션** — 리뷰 카테고리와 기준을 JSON 설정으로 쉽게 변경. AHOY는 eval_dispatch.py 코드 수정 필요
3. **Ticket Compliance 검증** — Jira/GitHub Issues와 연동하여 요구사항 충족도 자동 확인. AHOY의 contract.md 기반 검증보다 외부 시스템 통합이 강함
4. **적응형 토큰 압축** — 대형 PR도 단일 호출로 처리하는 효율적 압축 전략
5. **Incremental Review** — PR 업데이트 시 변경된 부분만 재리뷰. AHOY는 전체 재평가

### AHOY가 더 나은 점

1. **Generator-Evaluator 분리** — PR-Agent는 단일 LLM이 리뷰를 수행하여 자기평가 편향에 취약. AHOY는 생성자와 평가자를 구조적으로 분리
2. **다중 모델 컨센서스** — PR-Agent는 다중 모델 지원은 하지만 동시 평가/합의 메커니즘 없음. "하나라도 fail → 최종 fail" 규칙 부재
3. **상태머신 기반 워크플로우** — PR-Agent는 상태 없는 단일 호출 방식. 스프린트 사이클, rework 제한 등 없음
4. **파일 소유권 분리** — PR-Agent에는 파일 쓰기 권한 분리 개념 자체가 없음
5. **Generator 의견 strip** — PR-Agent의 리뷰 결과에는 모델의 주관적 판단이 그대로 포함됨

### 배울 만한 구체적 아이디어

1. **Severity 기반 우선순위 정렬**
   - PR-Agent는 findings를 심각도로 정렬하여 블로커를 먼저 표시
   - **적용**: `eval_dispatch.py`에서 issues.json 생성 시 `severity` 필드 기반 정렬 추가. `critical` → `major` → `minor` 순서

2. **Ticket Compliance 검증 통합**
   - contract.md의 요구사항과 생성 코드의 매칭도를 자동 점수화
   - **적용**: `eval_dispatch.py`에 contract.md 파싱 → 요구사항별 충족 여부 체크 → compliance_score 필드 추가

3. **Incremental Evaluation**
   - rework 시 변경된 부분만 재평가하여 비용/시간 절감
   - **적용**: `eval_dispatch.py`에서 이전 평가 결과 캐싱 + diff 기반 부분 재평가 로직

4. **JSON 기반 평가 설정 외부화**
   - 평가 카테고리, 가중치, 임계값을 JSON 설정 파일로 분리
   - **적용**: `eval_config.json` 신규 생성, eval_dispatch.py가 로드하여 평가 기준 동적 변경 가능

---

## AHOY 개선 제안 Top 3

### 1. Incremental Evaluation (부분 재평가)

**문제**: 현재 rework 시 전체 코드를 재평가하여 비용과 시간 낭비

**제안**: rework 시 변경된 파일/함수만 선별하여 재평가

**구현 방향**:
- `eval_dispatch.py`에 이전 평가 결과 캐시 저장 (`.ahoy/eval_cache/`)
- rework 시 `git diff` 기반으로 변경 범위 탐지
- 변경된 파일만 평가 모델에 전송, 미변경 파일은 캐시 결과 재사용
- issues.json에 `evaluation_scope: "incremental" | "full"` 필드 추가

### 2. JSON 기반 평가 설정 외부화

**문제**: 평가 기준 변경 시 eval_dispatch.py 코드 수정 필요

**제안**: 평가 카테고리, 심각도 기준, 가중치를 외부 JSON으로 관리

**구현 방향**:
- `eval_config.json` 신규 생성:
  ```json
  {
    "categories": ["security", "performance", "correctness", "style"],
    "severity_levels": ["critical", "major", "minor"],
    "max_findings_per_category": 5,
    "model_weights": {"codex": 0.5, "gemini": 0.5},
    "consensus_threshold": 2
  }
  ```
- `eval_dispatch.py`가 시작 시 설정 로드
- contract.md에 이슈별 오버라이드 가능

### 3. Severity 기반 이슈 우선순위 시스템

**문제**: issues.json의 이슈들이 우선순위 없이 나열됨

**제안**: 평가 모델의 findings에 severity를 부여하고, 컨센서스 시 severity도 합산

**구현 방향**:
- 평가 프롬프트에 severity 분류 지시 추가 (critical/major/minor)
- `eval_dispatch.py`에서 두 모델의 severity를 비교, 더 높은 등급 채택
- issues.json에 `severity` 필드 추가, critical이 하나라도 있으면 즉시 fail
- Generator에게 피드백 시 critical 이슈부터 우선 전달
