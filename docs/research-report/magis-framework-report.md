# MAGIS Framework 분석 리포트

> 분석일: 2026-03-28 (3차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | MAGIS (Multi-Agent for GitHub Issue reSolution) |
| GitHub URL | https://github.com/co-evolve-lab/magis |
| 스타 | 11 |
| 최근 커밋 | 2024-10-27 (3 commits 총, **비활성 — 학술 프로젝트**) |
| 라이선스 | 미명시 |
| 언어 | Python 3.11 |
| 발표 | NeurIPS 2024 |

## 핵심 아키텍처

### 4-에이전트 역할 분리 구조

```
Manager → Repository Custodian → Developer → QA Engineer
  (계획)     (코드베이스 탐색)      (코드 생성)   (검증)
```

1. **Manager**: 이슈를 분석하고 해결 계획 수립. 하위 에이전트에게 태스크 분배
2. **Repository Custodian**: 코드베이스 구조 파악, 관련 파일/함수 식별
3. **Developer**: 실제 코드 패치 생성
4. **QA Engineer**: 생성된 패치 검증

### 상태 관리
- Redis 캐싱 (v5.0.3)으로 LLM 요청 중복 제거
- `database_manager.py`로 에이전트 간 상태 공유
- `log.py`로 에이전트 활동 추적

### 평가 방식
- SWE-bench 벤치마크 기반 성능 측정
- GPT-4 직접 적용 대비 **8배 해결률** (13.94%)
- GPT-3.5, GPT-4, Claude-2와 비교

### 주요 파일

| 파일 | 용도 |
|------|------|
| `magis.py` | 메인 진입점 |
| `chat_with_LLM.py` | LLM 통신 레이어 |
| `operate.py` | 액션 실행 모듈 |
| `database_manager.py` | 상태 및 데이터 영속화 |
| `member.py` / `manager.py` / `custodian.py` / `quality_assurance.py` | 에이전트 구현 |
| `visual_web_page/` | Flask 기반 시각화 대시보드 |

## AHOY 대비 비교

### MAGIS가 AHOY보다 나은 점

1. **Repository Custodian 역할**: AHOY에는 없는 "코드베이스 탐색 전문 에이전트". Generator가 contract.md만 참조하는 반면, MAGIS는 전담 에이전트가 관련 파일/함수를 사전에 식별하여 Developer에게 전달. → **Generator 컨텍스트 자동 패킹과 유사하나 에이전트 수준에서 해결**
2. **시각화 대시보드**: Flask 기반 웹 UI로 멀티 에이전트 처리 워크플로우를 실시간 시각화. AHOY의 터미널 기반 상태 확인보다 직관적
3. **SWE-bench 통합**: 표준화된 벤치마크로 성능 정량 측정. AHOY에는 하네스 자체의 성능 벤치마크가 없음
4. **Redis 기반 요청 중복 제거**: LLM API 호출 비용을 자동으로 절감하는 캐싱 레이어

### AHOY가 MAGIS보다 나은 점

1. **Generator-Evaluator 구조적 분리**: MAGIS의 QA Engineer는 같은 LLM (GPT-4)을 사용하므로 자기평가 편향 존재. AHOY는 다른 모델로 평가
2. **다중 모델 컨센서스**: MAGIS는 단일 QA 에이전트. AHOY는 최소 2개 외부 모델 합의 필수
3. **Hook 기반 하드 차단**: MAGIS에는 상태 전이 강제 메커니즘 없음. 에이전트가 규칙을 무시할 수 있음
4. **파일 소유권 분리**: MAGIS는 모든 에이전트가 동일 파일 시스템에 접근. 물리적 쓰기 권한 분리 없음
5. **컨텍스트 리셋**: 세션 인계 메커니즘 없음. 긴 이슈에서 컨텍스트 오염 가능
6. **스프린트 상태머신**: 명시적 상태 전이 규칙 없음
7. **프로젝트 활성도**: 3 커밋, 2024년 이후 업데이트 없음. 학술 프로젝트로 실전 활용 한계

### 배울 만한 구체적 아이디어

1. **Repository Custodian 패턴 → Generator 전처리 단계**
   - `contract.md` 키워드 기반으로 코드베이스를 탐색하는 전처리 스크립트 추가
   - `custodian.py`의 파일 식별 로직을 `eval_dispatch.py`의 pre-generation 단계에 이식
   - 기존 제안 "Generator 컨텍스트 자동 패킹"의 구체적 참조 구현

2. **LLM 요청 캐싱 레이어**
   - `eval_dispatch.py`에 Redis/SQLite 캐싱 추가
   - 동일 파일의 재평가 시 이전 결과 재사용 → rework 비용 절감
   - 캐시 키: `hash(file_content + eval_prompt + model_name)`

3. **표준 벤치마크 기반 자가 측정**
   - SWE-bench lite 등으로 AHOY 하네스의 성능을 정기 측정
   - 하네스 변경 전후 해결률 비교로 개선 효과 정량화

---

## AHOY 개선 제안 Top 3

### 1. Repository Custodian 기반 Generator 컨텍스트 프리페치
- **구현 대상**: `eval_dispatch.py` (pre-generation 단계 추가)
- **변경 내용**: `contract.md`의 키워드/파일 패턴을 파싱하여 관련 소스 파일 목록을 자동 생성, Generator 프롬프트에 첨부
- **효과**: Generator가 관련 코드를 이미 알고 시작하므로 rework 감소
- **참조**: MAGIS `custodian.py`, Atlas Guardrails 컨텍스트 패킹

### 2. 평가 결과 캐싱 레이어
- **구현 대상**: `eval_dispatch.py`
- **변경 내용**: `hash(파일내용 + 평가프롬프트 + 모델명)` 키로 SQLite 캐시 저장. rework 시 변경되지 않은 파일은 캐시된 결과 재사용
- **효과**: rework 시 평가 API 비용 30-50% 절감, 평가 시간 단축
- **참조**: MAGIS Redis 캐싱, Qodo PR-Agent Incremental Evaluation

### 3. AHOY 자체 성능 벤치마크 시스템
- **구현 대상**: 새 파일 `benchmark/` 디렉토리
- **변경 내용**: SWE-bench lite 등 표준 벤치마크 태스크를 AHOY 스프린트로 실행, 해결률/rework 횟수/평가 정확도를 측정하는 자동화 스크립트
- **효과**: 하네스 변경의 효과를 정량적으로 검증 가능
- **참조**: MAGIS SWE-bench 통합
