# NeMo Guardrails (NVIDIA) 분석 리포트

> 분석일: 2026-03-28

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **프로젝트명** | NeMo Guardrails |
| **GitHub URL** | https://github.com/NVIDIA-NeMo/Guardrails |
| **스타** | ~5.9k |
| **최근 활동** | 마지막 릴리스 v0.21.0 (develop 브랜치 활발) |
| **언어** | Python |
| **라이선스** | Apache 2.0 |
| **특징** | Colang DSL 기반 프로그래머블 가드레일, 비동기 우선 설계 |

## 핵심 아키텍처

### Colang DSL (Domain Specific Language)

NeMo Guardrails의 핵심은 **Colang** — Python-like 대화 흐름 모델링 언어:

```colang
define user ask about politics
  "What do you think about the election?"
  "Who should I vote for?"

define flow politics
  user ask about politics
  bot refuse to respond
  bot offer to help with something else
```

- Colang 1.0 (기본) + Colang 2.0 지원
- `.co` 파일에 의도(intent), 봇 응답, 대화 흐름을 선언적으로 정의
- 비개발자도 이해 가능한 직관적 구문

### 5종 레일 시스템

가드레일을 5가지 유형으로 체계적 분류:

| 레일 유형 | 적용 시점 | 역할 |
|-----------|-----------|------|
| **Input Rails** | 사용자 입력 직후 | 악의적/부적절 입력 필터링 |
| **Dialog Rails** | LLM 프롬프팅 중 | 대화 흐름 가이드 |
| **Retrieval Rails** | RAG 청크 처리 시 | 검색 결과 필터/수정 |
| **Execution Rails** | 커스텀 액션 입출력 | 액션 모니터링 |
| **Output Rails** | LLM 응답 후 | 응답 검증/수정 |

### 런타임 강제 메커니즘

3가지 설정 파일의 조합으로 동작:
1. **`config.yml`** — 전역 설정, 모델 지정, 레일 활성화
2. **`actions.py`** — Python 커스텀 로직
3. **`.co` 파일** — Colang 흐름 정의

레일은 순차 실행: Input → Dialog → (Retrieval) → Output

### 비동기 우선 설계

```python
# 동기/비동기 모두 지원
rails = LLMRails(config)
response = rails.generate(messages)        # sync
response = await rails.generate_async(messages)  # async
```

- HTTP API 서버 모드: `nemoguardrails server`
- LangChain Runnable 호환

## AHOY와 비교 분석

### AHOY보다 나은 점

1. **선언적 DSL (Colang)** — 가드레일 규칙을 코드가 아닌 선언적 언어로 정의. 비개발자도 규칙 수정 가능. AHOY의 Hook은 Python/shell 코딩 필요
2. **5종 레일 분류 체계** — Input/Dialog/Retrieval/Execution/Output으로 가드레일을 적용 시점별 체계적 분류. AHOY는 PreToolUse/PostToolUse 2단계
3. **서버 모드 + HTTP API** — 가드레일을 독립 서비스로 배포 가능. AHOY는 로컬 프로세스 내장
4. **LangChain/RAG 통합** — RAG 파이프라인의 검색 결과에도 가드레일 적용. AHOY는 코드 생성-평가에 한정
5. **패턴 매칭 기반 의도 감지** — 사용자 입력 의도를 패턴으로 분류하여 사전 차단. AHOY의 Hook은 도구 호출 수준에서만 동작
6. **커뮤니티/기업 지원** — NVIDIA 공식 프로젝트, 5.9k 스타, 활발한 생태계

### AHOY가 더 나은 점

1. **코드 생성-평가 특화** — NeMo Guardrails는 대화형 AI 가드레일 범용 프레임워크로, 코드 생성 품질 평가에는 특화되지 않음
2. **다중 모델 컨센서스** — NeMo는 단일 LLM 호출 기반. 다중 모델 합의/교차 검증 메커니즘 없음
3. **상태머신 기반 워크플로우** — NeMo는 대화 흐름 관리는 있지만, 스프린트 사이클/rework 제한 같은 개발 워크플로우 상태 관리 없음
4. **Generator-Evaluator 분리** — NeMo는 동일 시스템 내에서 생성과 검증이 이루어짐
5. **파일 소유권/의견 strip** — 코드 생성 컨텍스트의 이러한 분리 메커니즘은 NeMo의 설계 범위 밖
6. **적대적 평가** — NeMo는 방어적 가드레일에 초점, AHOY는 적대적 평가(평가자가 문제를 적극적으로 찾아내는)에 초점

### 배울 만한 구체적 아이디어

1. **Colang-like 선언적 규칙 정의**
   - YAML/DSL로 Hook 규칙을 정의하면 비개발자도 가드레일 수정 가능
   - **적용**: `.ahoy/rules.yml` 파일에 규칙 선언:
     ```yaml
     rules:
       - name: block_force_push
         trigger: PreToolUse
         tool: Bash
         pattern: "git push --force"
         action: deny
         message: "Force push is not allowed"
     ```
   - Hook이 rules.yml을 파싱하여 동적으로 규칙 적용

2. **5단계 레일 적용 시점 분류**
   - AHOY의 Pre/PostToolUse를 더 세분화
   - **적용**:
     - **PrePlan Rail** — contract.md 작성 전 입력 검증
     - **PreGenerate Rail** — 코드 생성 전 스코프 확인
     - **PostGenerate Rail** — 생성 직후 기본 검증 (lint, type check)
     - **PreEvaluate Rail** — 평가 전 gen_report 정제
     - **PostEvaluate Rail** — 평가 결과 후처리

3. **비동기 평가 파이프라인**
   - 평가 모델 호출을 async로 병렬 실행
   - **적용**: eval_dispatch.py를 asyncio 기반으로 리팩터링, Codex와 Gemini 평가를 동시 실행하여 평가 시간 단축

4. **서버 모드 평가 서비스**
   - eval_dispatch.py를 독립 HTTP 서비스로 분리
   - **적용**: FastAPI 기반 평가 서버 구축, Claude Code Hook이 HTTP 호출로 평가 요청. 여러 프로젝트에서 공유 가능

---

## AHOY 개선 제안 Top 3

### 1. 선언적 가드레일 규칙 DSL

**문제**: Hook 규칙이 Python/shell 코드에 하드코딩되어 수정 시 코드 변경 필요

**제안**: NeMo의 Colang에서 영감받은 YAML 기반 규칙 정의 시스템

**구현 방향**:
- `.ahoy/rules.yml` 파일 신규 생성:
  ```yaml
  version: 1
  rails:
    pre_tool_use:
      - name: block_secrets_write
        tool: [Write, Edit]
        path_pattern: "*.env|*secret*|*credential*"
        action: deny

      - name: scope_enforcement
        tool: [Write, Edit]
        allowed_paths: "${contract.allowed_paths}"
        action: deny_if_outside

    post_tool_use:
      - name: strip_opinion
        tool: [Read]
        target: gen_report
        action: filter
        remove_patterns: ["I think", "seems like", "probably"]
  ```
- `hooks/rule_engine.py` — YAML 파서 + 규칙 매칭 엔진 (기존 Hook 대체)
- 기존 하드코딩 규칙을 YAML로 마이그레이션

### 2. 레일 적용 시점 세분화 (5-Rail 체계)

**문제**: PreToolUse/PostToolUse 2단계만으로는 워크플로우 전체를 세밀하게 제어하기 어려움

**제안**: NeMo의 5종 레일 개념을 AHOY 스프린트 사이클에 맞게 재설계

**구현 방향**:
- 5개 레일 포인트 도입:
  1. **ContractRail** — contract.md 생성/수정 시 스키마 검증
  2. **GenerateRail** — 코드 생성 중 허용 파일/디렉토리 강제
  3. **ReportRail** — gen_report 생성 시 의견 strip + 사실 검증
  4. **EvalRail** — 평가 모델 호출 전후 프롬프트/결과 정제
  5. **TransitionRail** — 상태 전이 시 전제조건 검증
- 각 레일에 대해 `rules.yml`에서 규칙 정의 가능
- 레일 실행 순서는 스프린트 상태에 따라 자동 결정

### 3. 비동기 병렬 평가 파이프라인

**문제**: 평가 모델 호출이 순차적이어서 2개 모델 평가 시 대기 시간 2배

**제안**: asyncio 기반 병렬 평가로 시간 단축

**구현 방향**:
- `eval_dispatch.py`를 async 리팩터링:
  ```python
  async def evaluate_parallel(code_bundle, contract):
      tasks = [
          evaluate_with_model("codex", code_bundle, contract),
          evaluate_with_model("gemini", code_bundle, contract),
      ]
      results = await asyncio.gather(*tasks, return_exceptions=True)
      return build_consensus(results)
  ```
- Rate limit 처리: 각 모델별 세마포어 + 자동 재시도
- 타임아웃 설정: 모델별 최대 대기 시간, 초과 시 해당 모델 결과 제외 + 경고
- 결과 수집 후 기존 컨센서스 로직 적용
