# GStack 분석 리포트

> 분석일: 2026-03-27

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | GStack |
| URL | https://github.com/garrytan/gstack |
| 스타 | 51.6k |
| 포크 | - |
| 라이선스 | MIT |
| 최근 활동 | 매우 활발 (2026-03-12 출시, 11일 만에 39k 스타) |
| 제작자 | Garry Tan (Y Combinator President & CEO) |

## 핵심 아키텍처

### 스프린트 기반 프로세스
**Think → Plan → Build → Review → Test → Ship → Reflect**

각 단계에 전용 도구가 있으며 이전 단계 출력이 다음 단계 입력으로 연결되는 파이프라인 구조.

### 역할 기반 페르소나 (20개 슬래시 커맨드)

**기획 & 전략**:
- `/office-hours`: 제품 아이디어 재구성, 구현 대안 + 노력 추정
- `/plan-ceo-review`: 4가지 모드(확장/선택적 확장/유지/축소)로 스코프 재검토
- `/plan-eng-review`: 아키텍처, 데이터 플로우, 엣지 케이스, 테스트 매트릭스 확정

**디자인**:
- `/plan-design-review`: 디자인 차원별 0-10 점수 + 인터랙티브 조정
- `/design-consultation`: 리서치부터 목업까지 완전한 디자인 시스템 구축
- `/design-review`: 디자인 이슈 감사 + before/after 검증

**개발 & 테스트**:
- `/review`: 프로덕션급 버그 발견, 자동 수정
- `/qa`: 실제 Chromium 브라우저 열어 버그 탐색, 리그레션 테스트 생성
- `/investigate`: 가설 테스트 기반 체계적 근본원인 디버깅

**보안**:
- `/cso`: OWASP Top 10 + STRIDE 위협 모델링. 8/10+ 신뢰도 게이팅으로 오탐 제로

**릴리스 & 운영**:
- `/ship`: main 동기화, 테스트, 커버리지 감사, PR 생성
- `/land-and-deploy`: PR 머지, CI 대기, 프로덕션 상태 확인
- `/document-release`: 배포 변경사항에 맞춰 문서 업데이트

**유틸리티**:
- `/browse`: 실제 Chrome 브라우저 자동화
- `/retro`: 주간 회고, 개인별 분석 + 트렌드 메트릭
- `/canary`: 배포 후 콘솔 에러/리그레션 모니터링
- `/benchmark`: Core Web Vitals, 리소스 크기 추적

### 안전장치
- `/careful`: 파괴적 명령어 사전 경고
- `/freeze`: 디버깅 중 특정 디렉토리만 수정 허용
- `/guard`: careful + freeze 결합
- `/codex`: OpenAI Codex CLI 독립 코드 리뷰 (크로스모델 분석)

### 다층 검증 시스템
1. 자동화된 게이트: 테스트 커버리지, CI, 구문 검증
2. 크로스모델 리뷰: Claude(`/review`) + Codex(`/codex`) 교차 평가
3. 실제 브라우저 테스트: Chromium으로 UX 버그 포착
4. 보안 스캔: 17개 오탐 배제로 고신뢰 발견
5. 디자인 감사: 인터랙티브 설문으로 인간 승인

## AHOY와 비교

### AHOY보다 나은 점
1. **풍부한 역할 페르소나**: 20개 슬래시 커맨드로 CEO/디자이너/QA/보안/릴리스 등 실제 팀 역할 모사. AHOY는 Generator/Evaluator 이분법
2. **실제 브라우저 테스트**: Chromium으로 실제 UX 검증. AHOY는 코드 레벨 평가만 수행
3. **크로스모델 리뷰 패턴**: `/review`(Claude) + `/codex`(OpenAI) 교차 리뷰가 간단하고 실용적
4. **배포 파이프라인 통합**: ship → land-and-deploy → canary까지 전체 배포 사이클 커버
5. **디자인 리뷰 시스템**: 정량적 점수(0-10) 기반 디자인 품질 평가
6. **`/freeze` 디렉토리 잠금**: 디버깅 중 의도치 않은 파일 수정 방지
7. **병렬 스프린트 지원**: Conductor로 10-15개 동시 스프린트 실행

### AHOY가 더 나은 점
1. **구조적 자기평가 차단**: GStack의 `/review`는 Claude가 자기 코드를 리뷰 (Codex 교차는 선택적). AHOY는 원천적으로 Generator≠Evaluator
2. **다중 모델 필수 컨센서스**: GStack의 크로스모델은 선택적. AHOY는 2개 이상 외부 모델 필수 합의
3. **Hook 기반 하드 차단**: GStack의 `/careful`, `/freeze`는 소프트 가드. AHOY Hook은 우회 불가능한 하드 차단
4. **파일 소유권 분리**: GStack은 파일 접근 제한 없음
5. **Generator 의견 strip**: GStack은 리뷰 결과에서 주관적 판단 필터링 없음
6. **rework 횟수 제한**: GStack은 무한 반복 가능. AHOY는 최대 3회로 제한

### 배울 만한 구체적 아이디어
1. **`/freeze` 디렉토리 잠금 패턴**: Hook에서 특정 디렉토리 외 Write 차단 → 디버깅 모드에서 관련 파일만 수정 가능하도록 스프린트별 스코프 제한
2. **신뢰도 게이팅 (8/10+)**: 보안 스캔 결과에 신뢰도 점수를 부여하고 임계값 이하는 자동 필터링 → eval_dispatch.py에서 평가 결과 신뢰도 점수 활용
3. **배포 후 Canary 모니터링**: 코드 생성 → 평가 → 배포 후 실제 동작 검증까지 확장

---

## AHOY 개선 제안 Top 3

### 1. 디렉토리 스코프 잠금 (Freeze 패턴) 도입
**현재 문제**: Generator가 스프린트 범위 외 파일을 수정할 수 있음
**구현 방향**:
- `contract.md`에 `allowed_paths` 필드 추가: 해당 스프린트에서 수정 가능한 파일/디렉토리 목록 명시
- `hooks/pre_tool_use.py`에서 Write/Edit 대상 경로가 allowed_paths 내인지 검증
- 범위 외 수정 시도 시 하드 차단 + 로그 기록

### 2. 평가 결과 신뢰도 점수 시스템
**현재 문제**: 평가가 pass/fail 이진 결과만 반환하여 경계 사례 판단이 어려움
**구현 방향**:
- `eval_dispatch.py`에서 각 평가 모델의 응답에 confidence score 요청 (0-10)
- `issues.json`에 `confidence` 필드 추가
- 컨센서스 로직 개선: 모든 모델 pass이지만 신뢰도 낮으면(< 7) 추가 검토 플래그
- rework 우선순위 결정에 신뢰도 활용

### 3. 실제 실행 환경 검증 단계 추가
**현재 문제**: 코드 레벨 평가만 수행하여 런타임 동작 검증 부재
**구현 방향**:
- 스프린트 상태머신에 `passed → verified` 단계 추가
- `verify_runner.py` 신규 생성: 생성된 코드를 실제 실행 + 테스트 스위트 구동
- 실행 결과를 eval_dispatch.py에 추가 입력으로 전달
- 런타임 에러 발생 시 자동 rework 트리거
