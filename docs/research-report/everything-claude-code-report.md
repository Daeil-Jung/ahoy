# Everything-Claude-Code 분석 리포트

> 분석일: 2026-03-27

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Everything-Claude-Code |
| URL | https://github.com/affaan-m/everything-claude-code |
| 스타 | 112k |
| 포크 | 14.5k+ |
| 기여자 | 30+ |
| 라이선스 | - |
| 최근 활동 | 매우 활발 (v1.9.0, 2026년 3월) |
| 기원 | Anthropic/Cerebral Valley 해커톤 (2026년 2월) |

## 핵심 아키텍처

### 규모
- **28개 전문 서브에이전트**: 언어별 (TypeScript, Python, Go, Java, Kotlin, C++, Rust, Perl, Swift, PHP)
- **125+ 스킬**: 도메인 워크플로우 및 패턴
- **60+ 커맨드**: 빠른 태스크 실행
- **포괄적 규칙 시스템**: 언어 패밀리별 구성
- **Hook 인프라**: 세션 라이프사이클 전반의 트리거 기반 자동화

### 보안 & 스캐닝
- AgentShield 통합 (`/security-scan`)
- 102개 보안 규칙, 1,282개 테스트
- 필수 보안 체크가 규칙에 내장
- 취약점 분석 전용 에이전트

### 평가 파이프라인
- 체크포인트 기반 + 연속 검증 모드
- Pass@k 메트릭 지원
- 세션 평가를 통한 패턴 추출
- Quality Gate + 구조화된 채점

### 멀티 에이전트 조율
- "반복적 검색 패턴"(Iterative Retrieval Pattern)으로 서브에이전트 오케스트레이션
- PM2 기반 서비스 라이프사이클 관리 (v1.4.0+)
- 컨텍스트 인지 위임으로 폭발 방지
- 순차, 캐스케이드, DAG 기반 실행 패턴

### 테스트
- 997+ 내부 테스트 통과 (v1.8.0)
- 언어별 TDD 워크플로우
- Playwright E2E 테스트 통합
- 커버리지 분석 커맨드

### 하네스 지원 범위
Claude Code (주), Cursor, OpenCode, Codex (앱+CLI), Antigravity IDE

### 주요 기능
- **토큰 최적화**: 모델 선택 + 시스템 프롬프트 슬리밍
- **메모리 지속성 Hook**: 크로스 세션 컨텍스트
- **연속 학습**: `/learn`, `/evolve` 커맨드로 패턴을 재사용 가능한 스킬로 추출
- **선택적 설치**: manifest 기반 컴포넌트 설치 (v1.9.0)

## AHOY와 비교

### AHOY보다 나은 점
1. **압도적 스케일**: 28 에이전트, 125+ 스킬, 60+ 커맨드. AHOY 대비 훨씬 넓은 커버리지
2. **다중 IDE/에이전트 지원**: Claude Code, Cursor, OpenCode, Codex 등 5개 환경 지원. AHOY는 Claude Code 전용
3. **Hook 인프라 성숙도**: 세션 라이프사이클 전반의 트리거 기반 자동화. AHOY Hook보다 이벤트 종류 풍부 (20+ 이벤트 타입)
4. **연속 학습 시스템**: `/learn`, `/evolve`로 세션에서 패턴 추출 → 스킬로 축적. AHOY에 해당 기능 없음
5. **Pass@k 메트릭**: 평가 품질의 정량적 측정. AHOY는 pass/fail 이진 결과만
6. **PM2 서비스 관리**: 프로세스 수준 에이전트 관리. AHOY는 프로세스 관리 없음
7. **선택적 설치**: 필요한 컴포넌트만 설치. AHOY는 전체 설치
8. **DAG 기반 실행**: 의존관계 그래프 기반 태스크 실행. AHOY는 선형 스프린트

### AHOY가 더 나은 점
1. **Generator-Evaluator 원칙적 분리**: ECC는 같은 모델이 생성+평가 가능. 자기평가 편향 구조적 미해결
2. **다중 독립 평가자 필수 컨센서스**: ECC의 Quality Gate는 단일 평가. AHOY는 2+ 외부 모델 합의 필수
3. **파일 소유권 강제 분리**: ECC는 모든 에이전트가 모든 파일 접근 가능
4. **Generator 의견 strip**: 주관적 판단 필터링 메커니즘 없음
5. **계약 기반 개발**: contract.md 같은 명시적 공통 참조점 없음
6. **스프린트 상태머신 엄격성**: 상태 전이 규칙이 soft하여 우회 가능성
7. **rework 횟수 제한**: 무한 루프 방지 메커니즘 미약
8. **컨텍스트 리셋 전략**: 정기적 handoff 문서 인계 방식 없음

### 배울 만한 구체적 아이디어
1. **Pass@k 메트릭 도입**: eval_dispatch.py에서 동일 태스크를 k번 평가하여 통과율 측정. 평가 신뢰도를 정량화
2. **연속 학습 패턴**: 스프린트 완료 시 성공/실패 패턴을 자동 추출하여 다음 스프린트 contract.md에 반영
3. **DAG 기반 태스크 실행**: 복수 이슈가 독립적일 때 병렬 평가 가능 → eval_dispatch.py에 의존관계 그래프 추가
4. **선택적 Hook 프로파일**: `ECC_HOOK_PROFILE` 환경변수로 상황별 Hook 세트 전환 → AHOY에도 스프린트 단계별 Hook 프로파일 적용

---

## AHOY 개선 제안 Top 3

### 1. Pass@k 평가 메트릭 도입
**현재 문제**: 평가가 단일 실행 pass/fail로 결정되어 비결정적 평가 결과에 취약
**구현 방향**:
- `eval_dispatch.py`에 `evaluation_k` 파라미터 추가 (기본값 3)
- 동일 코드에 대해 k번 독립 평가 실행
- 통과율 (pass@k) 계산 후 임계값(예: 2/3 이상) 기준으로 최종 판정
- `issues.json`에 `pass_at_k` 필드 추가: `{"k": 3, "passed": 2, "rate": 0.67}`

### 2. 스프린트 학습 축적 시스템
**현재 문제**: 매 스프린트 평가 결과가 축적되지 않아 반복되는 실수 패턴 학습 불가
**구현 방향**:
- `learning/patterns.json` 신규 파일: 스프린트별 실패 패턴 기록
- `eval_dispatch.py` 후처리에서 fail 원인 분류 + 패턴 등록 로직 추가
- contract.md 생성 시 관련 과거 실패 패턴을 자동 참조 섹션으로 삽입
- handoff 문서에 학습된 패턴 요약 포함

### 3. Hook 프로파일 시스템
**현재 문제**: 모든 스프린트 단계에서 동일한 Hook 세트 적용
**구현 방향**:
- `config.json`에 `hook_profiles` 섹션 추가: `{"planning": [...], "generation": [...], "evaluation": [...]}`
- `hooks/hook_manager.py` 신규 생성: 현재 스프린트 단계에 따라 활성 Hook 자동 전환
- 예: planning 단계에서는 파일 쓰기 차단 강화, evaluation 단계에서는 Generator 접근 차단 강화
