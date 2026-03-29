# OpenSWE (GAIR-NLP) 분석 리포트

> 분석일: 2026-03-28 (6차)

## 프로젝트 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | OpenSWE |
| URL | https://github.com/GAIR-NLP/OpenSWE |
| 스타 | ~500+ (추정, 학술 프로젝트) |
| 최근 활동 | 활발 (2025-2026 논문 기반) |
| 라이선스 | 학술 라이선스 |
| 규모 | 45,320 Docker 환경, 12.8k 리포지토리 |

## 핵심 아키텍처

### 품질 중심 필터링 파이프라인 (Quality-Centric Filtering Pipeline)

OpenSWE의 핵심은 SWE-bench 스타일 데이터셋을 대규모로 생성하되, **품질 필터링**으로 노이즈를 제거하는 파이프라인이다:

1. **환경 구축 (Construction)**: 12.8k 리포지토리에서 45,320개 실행 가능 Docker 환경 자동 생성
2. **난이도 특성화 (Difficulty Characterization)**: 각 환경의 고유 난이도를 자동 측정
3. **필터링 (Filtering)**: 풀 수 없는(unsolvable) 인스턴스와 너무 쉬운(trivial) 인스턴스 제거
   - PR-Issue 정렬 불일치 감지
   - 사소한 변경 감지 (trivially simple)
   - 환경 실행 불가 감지
4. **궤적 큐레이션 (Trajectory Curation)**: ~13,000개 큐레이션된 궤적, ~9,000 고품질 환경

### 다단계 품질 보장

- **환경 레벨**: Docker 빌드 성공 + 테스트 실행 성공 검증
- **태스크 레벨**: PR-Issue 정렬, 변경 크기, 복잡도 기반 난이도 분류
- **궤적 레벨**: 에이전트 해결 궤적의 품질 기반 필터링 및 큐레이션
- **모델 레벨**: SFT 학습 후 SWE-bench Verified에서 SOTA 달성 (62.4%/66.0%)

### 규모와 비용

- 환경 구축: $891K
- 궤적 샘플링 + 큐레이션: $576K
- 총 투자: ~$1.47M → 13,000 큐레이션 궤적

## AHOY와의 비교

### AHOY보다 나은 점

1. **태스크 난이도 정량화**: OpenSWE는 각 태스크의 고유 난이도를 자동 측정. AHOY는 태스크 복잡도에 대한 정량적 측정이 없어 모든 스프린트에 동일한 평가 강도 적용
2. **PR-Issue 정렬 검증**: 요구사항(Issue)과 구현(PR)의 정렬을 자동 검증. AHOY의 contract↔code 동기화 감사보다 체계적
3. **대규모 통계 기반 품질 기준**: 45K 환경에서 추출한 통계 기반 품질 임계값. 경험적으로 검증된 필터링 기준
4. **재현 가능한 평가 환경**: Docker 기반 완전 격리 환경에서 실행+테스트. AHOY는 로컬 환경 의존
5. **궤적 큐레이션**: 에이전트 행동 궤적 자체를 품질 평가하여 학습 데이터로 활용. AHOY는 결과만 평가

### AHOY가 더 나은 점

1. **실시간 하드 차단**: OpenSWE는 사후 필터링(batch). AHOY는 Hook으로 실시간 차단
2. **Generator-Evaluator 분리**: OpenSWE는 동일 모델이 생성+자기평가. AHOY의 외부 모델 평가가 편향에 강함
3. **다중 모델 컨센서스**: OpenSWE는 단일 모델 평가. AHOY의 2+ 모델 합의 필수가 더 견고
4. **파일 소유권/쓰기 제한**: OpenSWE에는 없음. AHOY의 issues.json 쓰기 분리가 무결성 보장
5. **스프린트 상태머신**: OpenSWE는 일회성 파이프라인. AHOY의 반복적 스프린트 사이클이 점진적 개선에 적합

## 배울 만한 구체적 아이디어

### 1. 태스크 난이도 자동 분류 (Task Difficulty Scoring)
- **현재 AHOY**: 모든 스프린트에 동일 평가 강도
- **제안**: contract.md 분석으로 태스크 난이도 자동 산출 (변경 파일 수, 의존성 깊이, API 복잡도)
- **구현**: `contract_analyzer.py` 신규 생성, contracted 진입 시 난이도 점수 산출

### 2. PR-Issue 정렬 자동 검증 (Alignment Verification)
- **현재 AHOY**: contract↔code 수동 확인
- **제안**: generated 상태에서 contract.md의 각 요구사항과 실제 변경 코드의 의미적 정렬 자동 검증
- **구현**: eval_dispatch.py에 alignment_check 단계 추가

### 3. Docker 기반 평가 격리 (Isolated Evaluation Environment)
- **현재 AHOY**: 로컬 환경에서 평가
- **제안**: 평가 시 Docker 컨테이너에서 코드 실행+테스트, 결과만 추출
- **구현**: `eval_sandbox/` 디렉토리에 Dockerfile + eval_runner.py

## AHOY 개선 제안 Top 3

### 1. 태스크 난이도 기반 평가 강도 자동 조절
- **파일**: `contract_analyzer.py` (신규), `eval_dispatch.py` 수정
- **구현**: contract.md 파싱 → (변경 파일 수 × 의존성 깊이 × API 표면적) → 난이도 점수 1-10 산출 → 점수에 따라 평가자 수(2-4), 평가 라운드 수(1-2), 세부 검사 항목 자동 결정
- **효과**: 간단한 태스크에 과도한 평가 비용 절감, 복잡한 태스크에 충분한 평가 보장

### 2. Contract-Code 의미적 정렬 검증 (Semantic Alignment Check)
- **파일**: `eval_dispatch.py`에 `alignment_check()` 함수 추가
- **구현**: generated 상태 진입 시 contract.md 요구사항을 항목별 추출 → 각 항목에 대응하는 코드 변경 존재 여부를 LLM으로 검증 → 미구현 항목 자동 탐지 → issues.json에 alignment_gap으로 기록
- **효과**: "요구사항은 있지만 구현 누락" 패턴 자동 감지, contract 대비 완성도 정량화

### 3. 평가 환경 Docker 격리
- **파일**: `eval_sandbox/Dockerfile` (신규), `eval_sandbox/runner.py` (신규), `eval_dispatch.py` 수정
- **구현**: generated 코드를 Docker 컨테이너에 마운트 → 테스트 실행 → 결과 JSON 추출 → 컨테이너 자동 정리. 로컬 환경 오염 없이 안전한 코드 실행 검증
- **효과**: 평가 재현성 보장, 악의적/부주의한 코드로부터 호스트 보호
