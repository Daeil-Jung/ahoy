# trailofbits/claude-code-config 분석 리포트

> 분석일: 2026-03-28 (5차)

## 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 프로젝트명 | claude-code-config |
| URL | https://github.com/trailofbits/claude-code-config |
| 스타 | 1,700 |
| 최근 커밋 | 2025-02 |
| 소속 | Trail of Bits (보안 감사 전문 기업) |
| 핵심 키워드 | Anti-Rationalization Gate, OS 샌드박싱, Mutation Audit Log, 프로젝트 MCP 차단, Deny Rules |

## 핵심 아키텍처

### 보안 계층 (Defense-in-Depth)

```
Layer 1: OS-Level Sandbox
  └─ /sandbox 커맨드 또는 devcontainer/원격 droplet
       ↓
Layer 2: Permission Deny Rules
  ├─ SSH 키 (.ssh/*)
  ├─ 클라우드 자격증명 (.aws/*, .gcloud/*)
  ├─ 셸 설정 (.bashrc, .zshrc)
  ├─ 암호화폐 지갑
  └─ 환경 변수 파일 (.env)
       ↓
Layer 3: PreToolUse Hooks (차단)
  ├─ rm -rf → trash 대안 제시
  └─ main/master 직접 push 차단
       ↓
Layer 4: PostToolUse Hooks (감사)
  └─ GAM 명령 분류 (read/write mutation) + 감사 로그
       ↓
Layer 5: Stop Hook (Anti-Rationalization Gate) ★
  └─ Claude가 작업 포기 감지 → 강제 계속
```

### Anti-Rationalization Gate (가장 독창적 기능)

Stop Hook에서 프롬프트 기반 평가를 사용하여 **Claude가 핑계를 대고 작업을 포기하는 것을 감지**:

- Claude가 "이 정도면 충분합니다" 또는 "나머지는 수동으로 하세요"라고 말할 때 개입
- 실제 완료 여부를 프롬프트로 평가
- 합리적 완료가 아닌 "합리화 포기"로 판단되면 강제 계속

**AHOY의 Generator 의견 strip과 유사한 문제 해결**: Generator가 어려운 작업을 회피하는 패턴 차단

### 설정 철학

| 설정 | 값 | 이유 |
|------|-----|------|
| 텔레메트리 | 비활성화 | 프라이버시 |
| Extended Thinking | 기본 활성 | 품질 향상 |
| 대화 기록 보존 | 365일 | 장기 감사 |
| 프로젝트 MCP 서버 | 비활성화 | 악의적 git-shipped 서버 방지 |

### CLAUDE.md 코딩 표준

- 함수 길이 제한 + 복잡도 임계값
- 언어별 도구 표준화: Python(uv/ruff), Node(oxlint), Rust(clippy)
- 테스트 방법론 요구사항
- 코드 리뷰 순서 규약
- 커밋/PR 워크플로우 표준

### Statusline 스크립트

2줄 상태바로 실시간 모니터링:
- 모델명, 컨텍스트 사용률 (색상 코딩), 세션 비용, 경과 시간, 프롬프트 캐시 적중률

### 로컬 모델 지원

LM Studio로 Qwen3-Coder-Next (80B MoE, 3B 활성 파라미터) 구동. Anthropic 호환 `/v1/messages` 엔드포인트.

## AHOY와 비교

### AHOY보다 나은 점

1. **Anti-Rationalization Gate**: Generator가 "이 정도면 됐다"라고 합리화하며 포기하는 것을 Stop Hook에서 감지. AHOY의 의견 strip은 보고서에서 주관적 판단을 제거하지만, 생성 단계에서의 조기 포기를 감지하지 않음
2. **OS 수준 샌드박싱**: Hook이 아닌 OS 수준에서 격리. AHOY의 Hook은 Claude Code 런타임 내부에서만 작동, OS 수준 탈출 방어 없음
3. **프로젝트 MCP 서버 기본 비활성화**: git clone 시 자동 로드되는 악의적 MCP 서버 차단. AHOY는 MCP 보안을 별도로 다루지 않음
4. **GAM Mutation Audit Log**: 모든 write 작업을 분류하여 감사 로그 유지. AHOY는 평가 결과만 기록, Generator의 모든 tool call 감사 없음
5. **Statusline 실시간 모니터링**: 컨텍스트 사용률/비용/캐시 적중률 실시간 표시. AHOY는 스프린트 진행 상태 시각화 없음
6. **보안 감사 전문 기업의 실전 노하우**: Trail of Bits의 보안 감사 워크플로우에서 검증된 설정

### AHOY가 더 나은 점

1. **Generator-Evaluator 분리**: Trail of Bits 설정은 단일 Claude 세션 내 자기검증. AHOY는 외부 모델 평가로 편향 차단
2. **다중 모델 컨센서스**: 단독 모델 판단에 의존. 복수 평가자 합의 없음
3. **상태머신 기반 스프린트**: Hook은 있지만 구조화된 개발 사이클 없음. AHOY의 planned→passed 상태머신이 더 체계적
4. **파일 소유권 분리**: Deny Rules는 민감 파일 읽기를 차단하지만, 평가 결과 파일의 쓰기 권한 분리는 없음
5. **계약 기반 개발**: contract.md 같은 명시적 요구사항 계약 없음

## 배울 만한 구체적 아이디어

### 1. Anti-Rationalization Gate (최고 우선순위)

Generator가 구현을 포기하는 패턴을 감지하는 Stop Hook:

```bash
# .claude/hooks/stop_anti_rationalization.sh
# Claude가 "수동으로 처리하세요", "이 정도면 충분", "TODO로 남깁니다" 등
# 회피성 종료를 시도할 때 개입

# 프롬프트 기반 평가:
# "이 종료가 합리적 완료인가, 아니면 어려운 부분을 회피한 것인가?"
```

**적용 파일**: `hooks/stop_hook.py` (신규) — Generator 세션 종료 시 합리화 포기 감지. Claudekit의 "코드→주석 대체 감지"와 결합 가능

### 2. OS 수준 샌드박싱 권장 설정

AHOY 설치 가이드에 샌드박스 실행 권장 사항 추가:

```yaml
# ahoy_config.yaml
sandbox:
  recommended: true
  method: "devcontainer"  # 또는 /sandbox
  deny_paths:
    - ~/.ssh/*
    - ~/.aws/*
    - ~/.config/gcloud/*
    - .env*
```

**적용 파일**: `AHOY_SETUP.md` + `config/ahoy_config.yaml` — 샌드박스 설정 가이드 추가

### 3. Tool Call Mutation 분류 감사 로그

Generator의 모든 tool call을 read/write로 분류하여 감사 기록:

```python
MUTATION_TYPES = {
    "Write": "write",
    "Edit": "write",
    "Bash": "classify_by_content",  # rm, mv, git push = write
    "Read": "read",
    "Glob": "read",
}
```

**적용 파일**: `hooks/post_tool_use.py` — tool call 분류 + SQLite 감사 로그 기록 (Overstory 제안과 결합)

---

## AHOY 개선 제안 Top 3

1. **Anti-Rationalization Gate (Stop Hook)** — Generator 세션 종료 시 "이 정도면 됐다" 류의 합리화 포기를 프롬프트 기반으로 감지. `hooks/stop_hook.py` 신규 추가. contract.md의 미완료 요구사항이 있는데 Generator가 종료하면 자동 개입. Claudekit의 코드→주석 대체 감지와 결합하면 Generator 회피 패턴 포괄적 차단

2. **프로젝트 MCP 서버 기본 비활성화 + MCP 허용 목록** — AHOY 설정에 `"projectMcpServers": "off"` 기본 적용. 필요한 MCP만 명시적 허용 목록으로 관리. Snyk Agent Scan의 Tool Poisoning 방어와 결합

3. **Tool Call Mutation 분류 감사 로그** — `hooks/post_tool_use.py`에서 모든 Generator tool call을 read/write로 분류, SQLite에 기록. 사후 감사 시 "Generator가 무엇을 수정했는지" 완전한 추적 가능. Evidence Pack 제안 + Overstory SQLite 감사 로그와 통합
