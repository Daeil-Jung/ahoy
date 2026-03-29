# duh (Multi-Model Consensus Engine) 분석 리포트

> 분석일: 2026-03-27

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | duh |
| URL | https://github.com/msitarzewski/duh |
| 스타 | 25 |
| 포크 | 10 |
| 커밋 | 54 |
| 최근 활동 | 소규모 프로젝트, 활성 개발 중 |

## 핵심 아키텍처

### 4단계 컨센서스 프로토콜
1. **Propose**: 가장 강력한 모델이 초기 응답 생성
2. **Challenge**: 다른 모델들이 강제 반박(forced disagreement)으로 결함 식별
3. **Revise**: 제안자가 유효한 도전을 반영하여 수정
4. **Commit**: 신뢰도 점수 + 보존된 반대 의견과 함께 최종 결정 추출

### 17개 모델 × 5개 프로바이더
- **Anthropic**: Claude Opus/Sonnet/Haiku
- **OpenAI**: GPT-5.4/5.2/5 mini/o3
- **Google**: Gemini 3.1 Pro/Flash
- **Mistral**: Large/Medium/Small/Codestral
- **Perplexity**: Sonar + reasoning 모델
- Ollama, LM Studio 로컬 모델도 OpenAI 호환 API로 지원

### 투표 프로토콜
다수결 또는 가중 합성. 모든 모델이 병렬로 독립 응답 후 집계.

### 검증 기능
- **아첨 감지 (Sycophancy Detection)**: 고무도장식 동의 플래그
- **인식론적 신뢰도 점수**: 도메인별 상한 (사실: 95%, 기술: 90%, 창의: 85%)
- **ECE (Expected Calibration Error)**: 시간 경과에 따른 캘리브레이션 개선 추적
- **소수 의견 추출**: 반대 의견을 별도 귀속하여 보존

### 통합 인터페이스
CLI, REST API, WebSocket 스트리밍, Python 클라이언트, MCP 서버, 3D 결정 공간 시각화 Web UI

## AHOY와 비교

### AHOY보다 나은 점
1. **Propose-Challenge-Revise-Commit 프로토콜**: 단순 다수결이 아닌 적대적 토론 기반 컨센서스. AHOY는 독립 평가 후 합의만 확인
2. **아첨 감지**: 평가자가 Generator에 동조하는 패턴 자동 탐지. AHOY에 해당 기능 없음
3. **인식론적 신뢰도 상한**: 도메인별 신뢰도 캡으로 과신 방지. AHOY는 pass/fail 이진
4. **소수 의견 보존**: 반대 의견을 별도 기록하여 추후 참조. AHOY는 컨센서스 결과만 기록
5. **ECE 추적**: 평가 캘리브레이션 품질의 시계열 개선 추적
6. **강제 반박 메커니즘**: Challenge 단계에서 의도적으로 결함을 찾도록 강제

### AHOY가 더 나은 점
1. **코딩 도메인 특화**: duh는 범용 컨센서스 엔진. 코드 생성/평가에 특화된 워크플로우 없음
2. **스프린트 상태머신**: duh는 상태 관리 없음. 단발성 쿼리-응답 구조
3. **Hook 기반 행동 제한**: 에이전트 행동 제한 메커니즘 없음
4. **파일 소유권 분리**: 파일 시스템 개념 자체가 없음
5. **Generator 의견 strip**: 생성자/평가자 분리 개념 없음 (모든 모델이 동등)
6. **계약 기반 개발**: 없음
7. **rework 사이클**: 단발성 질의응답이라 반복 수정 개념 없음

### 배울 만한 구체적 아이디어
1. **강제 반박(Forced Disagreement) 프롬프트**: 평가 모델에게 "이 코드의 문제점을 반드시 3개 이상 찾아라"는 지시 추가 → 아첨 편향 완화
2. **아첨 감지 알고리즘**: 평가자들의 동의율이 비정상적으로 높을 때 플래그 → eval_dispatch.py에 sycophancy detector 추가
3. **도메인별 신뢰도 상한**: 보안 평가 95%, 스타일 평가 80% 등 영역별 최대 신뢰도 설정
4. **소수 의견 보존**: issues.json에 minority_opinions 필드 추가하여 컨센서스와 다른 의견 기록

---

## AHOY 개선 제안 Top 3

### 1. 강제 반박(Forced Disagreement) 평가 프롬프트

> **v0.2.0 구현 완료** — `eval_dispatch.py:build_eval_prompt()` Forced Objection + Active Rejection 프롬프트 적용

**현재 문제**: 평가 모델이 코드가 "충분히 괜찮아 보이면" 쉽게 pass를 줄 수 있음 (아첨 편향)
**구현 방향**:
- `eval_dispatch.py`의 평가 프롬프트에 "이 코드에서 최소 3개의 잠재적 문제를 식별하라. 문제가 없다면 왜 없는지 구체적으로 설명하라" 추가
- Challenge 라운드: 첫 번째 평가자 결과를 두 번째 평가자에게 전달하며 "이 평가의 약점을 찾아라" 지시
- 최종 판정은 Challenge 후에도 유지되는 문제만 실제 issue로 등록

### 2. 아첨 감지 메커니즘
**현재 문제**: 외부 평가 모델이 Generator 코드에 과도하게 우호적일 수 있음
**구현 방향**:
- `eval_dispatch.py`에 `sycophancy_detector.py` 모듈 추가
- 평가 결과의 pass 비율을 이동평균으로 추적 (최근 10 스프린트)
- pass rate > 90%일 때 경고 플래그 + 평가 프롬프트 강화 자동 적용
- `metrics/eval_calibration.json`에 캘리브레이션 데이터 축적

### 3. 소수 의견(Minority Opinion) 보존 시스템
**현재 문제**: 컨센서스에서 탈락한 평가 의견이 유실되어 잠재적 이슈 추적 불가
**구현 방향**:
- `issues.json`에 `minority_opinions` 배열 필드 추가
- 컨센서스 fail이지만 한 모델만 지적한 문제를 별도 기록
- `gen_report`에 minority opinions 섹션 추가하여 Generator가 참고하도록 함
- 동일 minority opinion이 3회 이상 반복되면 자동으로 주요 이슈로 승격
