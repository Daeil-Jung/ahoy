# OpenGuardrails 분석 리포트

> 분석일: 2026-03-28 (3차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | OpenGuardrails |
| GitHub URL | https://github.com/openguardrails/openguardrails |
| 스타 | 322 |
| 최근 릴리스 | v6.8.21 (2026-03-12) — **매우 활발** |
| 커밋 | 447 |
| 라이선스 | Apache 2.0 |
| 언어 | TypeScript (85.8%) |
| 가격 | 무료 500회/일, $19-$199/월 |

## 핵심 아키텍처

### 2계층 탐지 시스템

```
┌─────────────────────────────────────────────┐
│              Static Detection                │
│  (에이전트 설정, 스킬 정의, 메모리 사전 스캔) │
└─────────────┬───────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│             Runtime Detection                │
│  Tool Call → Tool Result → LLM Request       │
│  → Behavioral Chain → Intent Mismatch        │
└─────────────────────────────────────────────┘
```

### 10종 콘텐츠 스캐너 (S01-S10)

| 스캐너 | 탐지 대상 |
|--------|-----------|
| S01 | Prompt Injection |
| S02 | System Override |
| S03 | Web Attacks |
| S04 | MCP Tool Poisoning |
| S05 | Malicious Code Execution |
| S06 | NSFW Content |
| S07 | PII Leakage |
| S08 | Credential Leakage |
| S09 | Confidential Data |
| S10 | Off-topic Drift |

### 행동 패턴 감지

단순 단일 이벤트가 아닌 **이벤트 체인** 패턴 감지:

| 패턴 | 설명 |
|------|------|
| File Read → Exfiltration | 파일 읽기 후 외부 전송 시도 |
| Credential Access → External Write | 자격증명 접근 후 외부 쓰기 |
| Shell Exec After Web Fetch | 웹 콘텐츠 가져온 후 셸 실행 |
| Intent-Action Mismatch | 의도와 실제 행동 불일치 |

### 주요 컴포넌트

| 디렉토리 | 용도 |
|----------|------|
| `moltguard/` | 핵심 보안 플러그인 |
| `gateway/` | AI Security Gateway (PII/자격증명 자동 제거) |
| `dashboard/` | 모니터링 및 분석 대시보드 |
| `standards/` | 탐지 규칙 정의 |

### AI Security Gateway

- LLM 요청에서 PII/자격증명을 토큰으로 자동 치환
- 응답에서 토큰을 원본으로 복원
- 데이터가 LLM 제공자에게 노출되지 않음

### v6.8.0 아키텍처 통합

- 단일 MoltGuard 플러그인으로 통합
- 독립 CLI 제거 → 플러그인 프로세스에 내장
- AI Security Gateway + Dashboard가 플러그인 내 임베드

## AHOY 대비 비교

### OpenGuardrails가 AHOY보다 나은 점

1. **행동 패턴 체인 감지**: 단일 이벤트가 아닌 이벤트 시퀀스 패턴 탐지. AHOY hook은 개별 tool call 수준만 검사
2. **Intent-Action Mismatch 감지**: Generator의 의도(프롬프트)와 실제 행동(tool call) 불일치 탐지. AHOY에는 의도-행동 일관성 검증 없음
3. **AI Security Gateway (PII 자동 제거)**: 평가 모델에 코드를 보낼 때 민감 데이터 자동 마스킹. AHOY는 평가 시 원본 코드 전송
4. **10종 전문 스캐너**: 각 위협 유형에 특화된 탐지 로직. AHOY hook은 범용적
5. **Static + Runtime 이중 방어**: 실행 전 설정 검사 + 실행 중 행동 감시. AHOY는 런타임만
6. **MCP Tool Poisoning 탐지**: MCP 서버 도구 정의 자체의 악의적 조작 감지. AHOY에는 해당 기능 없음
7. **대시보드**: 에이전트 활동 시간, 액션 수, LLM 호출 모니터링

### AHOY가 OpenGuardrails보다 나은 점

1. **Generator-Evaluator 분리**: OpenGuardrails는 보안 게이트키퍼일 뿐, 코드 품질 평가 기능 없음
2. **다중 모델 컨센서스**: 없음. 규칙 기반 단일 결정
3. **스프린트 상태머신**: 없음. 개별 이벤트/체인 감지에 특화
4. **코드 품질 평가**: 없음. 보안에 특화
5. **계약 기반 개발**: 없음. 워크플로우 관리 기능 없음
6. **로컬 완전 실행**: OpenGuardrails는 유료 클라우드 서비스 의존 (무료 500회/일 제한). AHOY는 로컬 실행

### 배울 만한 구체적 아이디어

1. **행동 패턴 체인 감지 → Hook 시퀀스 분석**
   - PostToolUse hook에서 최근 N개 tool call 히스토리를 유지
   - 위험 패턴 (예: `Read(.env) → Bash(curl)`) 자동 탐지
   - 패턴 정의를 YAML로 외부화하여 커스터마이징 가능

2. **Intent-Action Mismatch 감지**
   - contract.md의 요구사항과 Generator의 실제 tool call을 비교
   - "contract에 DB 관련 작업 없는데 DB 파일을 수정" 같은 불일치 탐지
   - `eval_dispatch.py`의 사전 검증 단계에 추가

3. **Static Pre-scan (사전 설정 검사)**
   - 스프린트 시작 전 프로젝트 설정 파일들을 사전 스캔
   - `.env`, 자격증명, 민감 파일 목록 자동 생성
   - Hook 규칙에 자동 반영하여 보호 범위 확대

4. **PII/Credential 마스킹**
   - 평가 모델에 코드를 보내기 전 민감 데이터 자동 마스킹
   - 평가 결과에서 마스킹 해제
   - 외부 API에 민감 데이터 노출 방지

---

## AHOY 개선 제안 Top 3

### 1. 행동 패턴 체인 감지 Hook
- **구현 대상**: `hooks/post_tool_use/` (새 훅 스크립트) + 세션 상태 파일
- **변경 내용**: PostToolUse hook에서 최근 10개 tool call을 JSON 파일에 기록. 미리 정의된 위험 패턴 (예: `Read(*.env) → Bash(curl|wget)`, `Read(*.key) → Write(*)`)과 매칭. 매칭 시 경고 또는 차단
- **효과**: 단일 tool call은 무해하지만 조합하면 위험한 시퀀스를 자동 감지
- **참조**: OpenGuardrails Behavioral Pattern Detection

### 2. Intent-Action Mismatch 검증

> **v0.2.0 구현 완료** — `validate_harness.py:audit_final_scope()` contract scope vs git diff 사후 대조 구현

- **구현 대상**: `eval_dispatch.py` (generated→passed 전이 시 추가 검증)
- **변경 내용**: contract.md의 `allowed_paths` / `scope` 정의와 Generator가 실제 수정한 파일 목록을 비교. 계약 범위 외 수정이 있으면 평가 전에 경고 플래그 추가
- **효과**: Generator의 범위 이탈을 평가 전에 조기 감지
- **참조**: OpenGuardrails Intent-Action Mismatch, 기존 제안 "디렉토리 스코프 잠금"의 런타임 버전

### 3. 평가 전 민감 데이터 마스킹
- **구현 대상**: `eval_dispatch.py` (평가 모델에 코드 전송 직전)
- **변경 내용**: 코드에서 API 키, 비밀번호, 연결 문자열 등을 정규식으로 탐지하여 `[MASKED_API_KEY_1]` 등으로 치환 후 평가. 평가 결과의 라인 참조는 원본 기준으로 역매핑
- **효과**: 외부 평가 모델(Codex/Gemini)에 민감 데이터 노출 방지
- **참조**: OpenGuardrails AI Security Gateway
