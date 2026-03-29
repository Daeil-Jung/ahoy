# coding-agent-eval 분석 리포트

> 분석일: 2026-03-28 (10차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | coding-agent-eval |
| GitHub URL | https://github.com/halton/coding-agent-eval |
| 스타 | ~10 (소규모) |
| 최근 커밋 | 2026년 3월 활성 |
| 라이선스 | 미확인 |
| 언어 | Python |

## 핵심 아키텍처

### 개요
coding-agent-eval은 Claude CLI, GitHub Copilot CLI, Gemini CLI 3개 코딩 에이전트를 동일 태스크에 대해 자동 벤치마킹하는 평가 프레임워크다.

### 구조
```
[프롬프트 파일] → [에이전트 디스패치 (Claude/Copilot/Gemini)]
                         ↓
              [코드 생성 (각 에이전트)]
                         ↓
              [수락 테스트 자동 실행]
                         ↓
              [HTML 리포트 생성]
```

### 핵심 특징

1. **다중 에이전트 자동 벤치마킹**: 동일 프롬프트를 Claude, Copilot, Gemini에 동시 전달하고 결과 비교
2. **지능형 수락 테스트**: 커스텀 `accept.sh` 우선, 없으면 Python 프로젝트는 pytest, Node.js는 npm test 자동 감지
3. **유연한 실행 모드**: 병렬(parallel) 또는 직렬(serial) 실행 선택
4. **HTML 리포트**: 성공률, 타이밍, 시각화 포함
5. **동적 태스크 로딩**: 프롬프트 파일에서 태스크 자동 발견
6. **날짜 기반 출력 디렉토리**: 실행 결과 자동 정리
7. **에이전트 권한 설정**: 안전 제한 포함 설정 가능

## AHOY와 비교

### AHOY보다 나은 점

1. **실제 에이전트 CLI 통합**: Claude CLI, Copilot CLI, Gemini CLI를 직접 호출하여 실제 환경에서 테스트. AHOY는 API 수준에서만 평가
2. **자동 테스트 감지**: 프로젝트 유형별(Python/Node.js) 테스트 프레임워크 자동 감지 및 실행. AHOY는 수동 설정 필요
3. **벤치마크 비교 리포트**: 에이전트 간 성능을 HTML 시각화로 직접 비교 가능. AHOY는 단일 에이전트(Generator) 평가에 집중
4. **날짜 기반 히스토리**: 실행 결과를 날짜별로 자동 정리, 시계열 성능 추적 가능

### AHOY가 더 나은 점

1. **Generator-Evaluator 분리**: coding-agent-eval은 생성과 평가가 동일 파이프라인. AHOY는 구조적으로 자기평가 편향 차단
2. **다중 모델 컨센서스**: coding-agent-eval은 단일 수락 테스트. AHOY는 최소 2개 외부 모델 합의 필요
3. **상태머신 기반 워크플로우**: coding-agent-eval은 단순 실행-테스트 2단계. AHOY는 planned→contracted→generated→passed 사이클
4. **Hook 기반 하드 차단**: coding-agent-eval에는 에이전트 행동 제어 메커니즘 없음. AHOY는 우회 불가능한 규칙 강제
5. **파일 소유권 분리**: coding-agent-eval은 파일 접근 제어 없음
6. **rework 사이클**: coding-agent-eval은 실패 시 단순 fail. AHOY는 최대 3회 rework 제공
7. **계약 기반 개발**: coding-agent-eval은 자유형 프롬프트. AHOY는 contract.md로 요구사항 명세화

## 배울 만한 구체적 아이디어

### 1. 자동 테스트 프레임워크 감지
```python
# eval_dispatch.py에 추가 가능
def detect_test_framework(project_path):
    if (project_path / "pytest.ini").exists() or (project_path / "setup.py").exists():
        return "pytest"
    elif (project_path / "package.json").exists():
        return "npm_test"
    elif (project_path / "accept.sh").exists():
        return "custom_script"
    return None
```
- `generated→passed` 전이에서 자동 감지된 테스트 실행

### 2. 에이전트 간 성능 비교 벤치마크
- AHOY의 평가자(Codex, Gemini)의 평가 품질을 정량화하는 벤치마크 시스템
- 동일 이슈에 대한 평가자 간 일치율/정확도 추적

### 3. 날짜 기반 실행 아카이브
- `.ahoy/archive/YYYY-MM-DD/sprint-{id}/` 구조로 스프린트 결과 자동 보존
- 시계열 성능 분석 가능

---

## AHOY 개선 제안 Top 3

### 1. 자동 테스트 프레임워크 감지 및 실행 (generated→passed 강화)
- **파일**: `eval_dispatch.py`
- **변경**: `generated→passed` 전이 시 프로젝트 루트를 스캔하여 pytest/npm test/커스텀 스크립트 자동 감지
- **효과**: LLM 평가 외에 결정론적 테스트 결과를 평가에 포함, 신뢰도 향상

### 2. 평가자 벤치마크 메타 평가 시스템
- **파일**: `eval_dispatch.py`, 신규 `eval_benchmark.py`
- **변경**: 알려진 정답이 있는 표준 태스크 세트로 Codex/Gemini의 평가 정확도를 주기적 측정
- **효과**: 평가자 자체의 품질 추적, 평가 편향 조기 감지

### 3. 스프린트 아카이브 시스템 (날짜 기반)
- **파일**: 신규 `.ahoy/archive/` 디렉토리 구조
- **변경**: `passed` 상태 도달 시 contract+issues+diff+평가결과를 `archive/YYYY-MM-DD/sprint-{id}/`에 자동 저장
- **효과**: 시계열 성능 분석, 회귀 감지, 감사 추적
