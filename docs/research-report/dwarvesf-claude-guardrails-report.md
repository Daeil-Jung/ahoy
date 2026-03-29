# dwarvesf/claude-guardrails 분석 리포트

> 분석일: 2026-03-28 (4차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | claude-guardrails (Dwarves Foundation) |
| GitHub URL | https://github.com/dwarvesf/claude-guardrails |
| 스타 | 8 |
| 최근 커밋 | 2026-03-01 |
| 라이선스 | MIT |
| 언어 | Shell 100% |
| 조직 | Dwarves Foundation (베트남 소프트웨어 에이전시) |

## 핵심 아키텍처

### 5계층 방어 모델

```
Layer 1: Permission Deny Rules (도구 접근 차단)
  → Layer 2: PreToolUse Hooks (위험 명령 차단)
    → Layer 3: OS-Level Sandbox (파일시스템/네트워크 격리)
      → Layer 4: PostToolUse Injection Scanner (Full만)
        → Layer 5: CLAUDE.md Security Rules (자연어 지침)
```

### Lite vs Full 변형

| 측면 | Lite | Full |
|------|------|------|
| **대상** | 신뢰할 수 있는 내부 프로젝트 | 신뢰할 수 없는 코드베이스, 프로덕션 |
| **Deny Rules** | 15개 (SSH, AWS, .env, 인증서) | 28개 (+GnuPG, 쉘 프로파일, secrets 디렉토리) |
| **PreToolUse Hooks** | 3개 (파괴적 삭제, git push, pipe-to-shell) | 5개 (+데이터 유출, 권한 상승) |
| **PostToolUse Scanner** | ❌ | ✅ (프롬프트 인젝션 감지) |
| **설치** | `npx claude-guardrails install` | `npx claude-guardrails install full` |

### Permission Deny Rules 상세

**Lite (15개)**:
- SSH 키 (`~/.ssh/`)
- AWS 자격증명 (`~/.aws/`)
- 환경 파일 (`.env`, `.env.*`)
- 인증서 파일 (`*.pem`, `*.key`)

**Full 추가 (13개)**:
- GnuPG (`~/.gnupg/`)
- 쉘 프로파일 (`~/.bashrc`, `~/.zshrc`)
- Secrets 디렉토리 (`secrets/`, `.secrets/`)

### PreToolUse Hooks 상세

| Hook | Lite | Full | 감지 대상 |
|------|------|------|---------|
| 파괴적 삭제 차단 | ✅ | ✅ | `rm -rf /`, `rm -rf ~` |
| 직접 git push 차단 | ✅ | ✅ | `git push` (PR 강제) |
| pipe-to-shell 차단 | ✅ | ✅ | `curl ... | bash` |
| 데이터 유출 감지 | ❌ | ✅ | 민감 파일 → 외부 전송 |
| 권한 상승 감지 | ❌ | ✅ | `chmod 777`, `sudo` 남용 |

### 설치/제거 메커니즘

- **설치**: `~/.claude/settings.json`에 jq 기반 수술적 병합 (기존 설정 보존)
- **백업**: 설치 전 자동 백업
- **제거**: 설치 시 추가한 항목만 정확히 제거 (surgical remove)
- **반복 실행 안전**: 여러 번 실행해도 중복 없음

### 알려진 제한사항

> "deny rules only cover Claude's built-in tools, not bash"

- `bash cat ~/.ssh/id_rsa`는 Read 권한 규칙을 우회
- **OS-Level Sandbox만이 진정한 강제 계층**
- Hook 실행 시 subshell + jq/grep 파이프로 지연 발생

## AHOY와의 비교

### AHOY보다 나은 점

| 영역 | dwarvesf/claude-guardrails | AHOY |
|------|---------------------------|------|
| **설치 편의성** | `npx` 한 줄로 즉시 설치 | 커스텀 설정 필요 |
| **단계적 보안** | Lite/Full 2단계로 프로젝트별 보안 수준 조절 | 일률적 설정 |
| **Deny Rules 체계** | 15-28개 경로 기반 접근 차단 | 파일 소유권은 issues.json만 |
| **수술적 설치/제거** | 기존 설정 보존하며 병합/제거 | 설정 관리 자동화 없음 |
| **프롬프트 인젝션 방어** | PostToolUse 출력 스캔 (Full) | 프롬프트 인젝션 방어 없음 |

### AHOY가 더 나은 점

| 영역 | AHOY | dwarvesf/claude-guardrails |
|------|------|---------------------------|
| **코드 품질 평가** | 다중 모델 컨센서스 평가 | 보안 차단만 (품질 무관) |
| **워크플로우 관리** | 스프린트 상태머신 | 워크플로우 없음 |
| **Generator-Evaluator 분리** | 구조적 편향 차단 | 단일 모델 사용 |
| **계약 기반 개발** | contract.md 기반 | 요구사항 관리 없음 |
| **동적 평가** | 외부 모델이 코드 품질 판단 | 정적 규칙만 (패턴 매칭) |
| **컨텍스트 리셋** | 핸드오프 문서 | 상태 관리 없음 |

### 핵심 차이

dwarvesf/claude-guardrails는 **"무엇을 하지 말아야 하는가"** (차단 목록)에 집중하고, AHOY는 **"무엇을 해야 하는가"** (계약 + 평가)에 집중한다. 둘은 보완적이다.

## 배울 만한 구체적 아이디어

### 1. 경로 기반 Deny Rules 체계화
```json
// .claude/settings.json에 추가
{
  "deny_rules": {
    "lite": ["~/.ssh/", "~/.aws/", ".env"],
    "full": ["~/.gnupg/", "~/.bashrc/", "secrets/"],
    "ahoy": ["issues.json", "eval_dispatch.py", "sprint_memory/"]
  }
}
```
- AHOY의 파일 소유권 분리를 deny rules 체계로 확장

### 2. Lite/Full 프로파일 시스템
- 스프린트 단계별로 다른 보안 프로파일 자동 적용
- `generated` 상태: strict (코드 생성 시 최대 제약)
- `passed` 상태: relaxed (통과 후 완화)

### 3. 수술적 설정 관리
- AHOY Hook 설치/제거를 자동화하는 CLI 도구
- 기존 사용자 설정을 보존하며 AHOY 설정만 병합/제거

---

## AHOY 개선 제안 Top 3

### 1. AHOY 파일 보호 Deny Rules 확장
- **현재**: issues.json만 파일 소유권 분리 (eval_dispatch.py만 쓰기 가능)
- **개선**: AHOY 핵심 파일 전체에 deny rules 적용
- **구현 방향**:
  - `.claude/settings.json`에 deny rules 추가:
    - `issues.json` — Generator 쓰기 금지 (기존)
    - `eval_dispatch.py` — Generator 수정 금지
    - `sprint_memory/` — Generator 직접 접근 금지
    - `eval_rubrics/` — 평가 루브릭 변조 방지
  - Hook이 아닌 Claude Code 네이티브 deny rules로 강제
  - 효과: Hook 우회 시나리오에서도 파일 보호

### 2. 단계적 보안 프로파일 (Lite/Full 패턴 차용)
- **현재**: 모든 스프린트에 동일한 Hook 규칙 적용
- **개선**: 스프린트 단계별 보안 수준 자동 전환
- **구현 방향**:
  - `security_profiles/` 디렉토리에 프로파일 정의
  - `strict.json` — generated 상태 (외부 파일 수정 금지, 테스트 실행 금지)
  - `standard.json` — contracted/planned 상태 (기본 규칙)
  - `relaxed.json` — passed 상태 (문서화/정리 허용)
  - 상태 전이 Hook에서 프로파일 자동 전환

### 3. AHOY CLI 설치/관리 도구
- **현재**: AHOY 설정을 수동으로 .claude에 배치
- **개선**: dwarvesf 방식의 npx/pip 한 줄 설치
- **구현 방향**:
  - `pip install ahoy-harness` 또는 `npx ahoy-harness install`
  - `ahoy install` — Hook + deny rules + 디렉토리 구조 자동 생성
  - `ahoy uninstall` — AHOY 설정만 수술적 제거
  - `ahoy status` — 현재 설정 상태 진단
  - 기존 .claude/settings.json 보존하며 병합
