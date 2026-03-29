# Snyk Agent Scan 분석 리포트

> 분석일: 2026-03-28 (4차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Snyk Agent Scan |
| GitHub URL | https://github.com/snyk/agent-scan |
| 스타 | 2,000 |
| 최근 릴리스 | v0.4.10 (2026-03-25) — 매우 활발 |
| 라이선스 | Apache-2.0 |
| 언어 | Python 90.1% |
| 설치 | `uvx snyk-agent-scan@latest` / Homebrew |

## 핵심 아키텍처

### 구조 개요

Snyk Agent Scan은 **에이전트 생태계 전체를 대상으로 한 보안 스캐너**로, 개별 코드가 아닌 에이전트 구성 요소(MCP 서버, 스킬, 도구 설정)를 탐지하고 감사한다.

```
Discovery (자동 탐지)
  → Connection (MCP 서버 stdio 연결)
    → Metadata Retrieval (도구 메타데이터 수집)
      → Verification (Snyk API 검증)
        → Report (JSON/리치텍스트 리포트)
```

### 2대 운영 모드

| 모드 | 설명 |
|------|------|
| **Scan Mode** | CLI 실행, 즉시 스캔 + 리포트 출력 |
| **Background Mode** | 주기적 백그라운드 스캔, Snyk Evo에 결과 보고 |

### 보안 위험 탐지 카테고리

#### MCP 서버 위협 (4종)
1. **Prompt Injection** — MCP 서버 도구 설명에 숨겨진 프롬프트 주입
2. **Tool Poisoning** — 악의적 도구 정의
3. **Tool Shadowing** — 기존 도구를 가로채는 섀도 도구
4. **Toxic Data Flows** — 안전하지 않은 데이터 흐름 경로

#### 에이전트 스킬 취약점 (5종)
1. **Prompt Injection** — 스킬 내 프롬프트 주입
2. **Malware Payloads** — 자연어에 숨겨진 악성 페이로드
3. **Untrusted Content Handling** — 신뢰할 수 없는 콘텐츠 처리
4. **Insecure Credential Management** — 안전하지 않은 자격 증명 관리
5. **Hardcoded Secrets** — 하드코딩된 비밀키

### 지원 플랫폼

| 플랫폼 | MCP 스캔 | 스킬 스캔 |
|--------|---------|---------|
| Claude Code | ✅ | ✅ |
| Claude Desktop | ✅ | ❌ |
| Cursor | ✅ | ✅ |
| Windsurf | ✅ | ✅ |
| VS Code | ✅ | ✅ |
| Gemini CLI | ✅ | ✅ |

### Skill Inspector (신규 기능)

- 웹 기반 셀프서비스 인터페이스
- 악성 스킬, 안전하지 않은 설정, 유출된 비밀 탐지
- CLI + 웹사이트 양방향 제공

## AHOY와의 비교

### AHOY보다 나은 점

| 영역 | Snyk Agent Scan | AHOY |
|------|-----------------|------|
| **공급망 보안** | MCP 서버/스킬/도구 설정 전체 스캔 | 생성 코드만 평가 |
| **Tool Poisoning 탐지** | MCP 도구 정의의 악의적 변조 감지 | MCP 도구 보안 검증 없음 |
| **Tool Shadowing 탐지** | 기존 도구를 가로채는 공격 감지 | 도구 무결성 검증 없음 |
| **멀티 플랫폼 지원** | 6+ 에이전트 플랫폼 자동 탐지 | Claude Code 전용 |
| **백그라운드 모니터링** | 주기적 자동 스캔 모드 | 스프린트 시점만 검증 |
| **엔터프라이즈 통합** | Snyk Evo 대시보드 연동 | 독립 실행만 |

### AHOY가 더 나은 점

| 영역 | AHOY | Snyk Agent Scan |
|------|------|-----------------|
| **코드 품질 평가** | 다중 모델 컨센서스로 코드 품질 검증 | 보안 취약점만 탐지 (품질 무관) |
| **워크플로우 관리** | 스프린트 상태머신으로 개발 사이클 관리 | 스캔만 수행 (워크플로우 없음) |
| **Generator-Evaluator 분리** | 생성과 평가의 구조적 분리 | 스캔 도구일 뿐 (생성 없음) |
| **계약 기반 개발** | contract.md로 기대 사항 명세 | 요구사항 관리 없음 |
| **상태 전이 강제** | Hook으로 하드 차단 | 리포트만 생성 (차단 없음) |
| **컨텍스트 리셋** | 3 스프린트마다 핸드오프 | 단발성 스캔 |

## 배울 만한 구체적 아이디어

### 1. MCP 도구 무결성 검증 (Tool Poisoning/Shadowing 방어)
```python
# Hook에서 MCP 서버의 도구 정의가 변조되지 않았는지 검증
class MCPToolIntegrityChecker:
    def __init__(self, trusted_manifest: dict):
        self.trusted = trusted_manifest  # 최초 등록 시 스냅샷

    def verify(self, current_tools: list) -> bool:
        """도구 정의 해시 비교로 변조 감지"""
        for tool in current_tools:
            if hash(tool.description) != self.trusted.get(tool.name):
                return False  # Tool Poisoning 감지
        return True
```

### 2. 에이전트 구성 요소 사전 스캔
- 스프린트 시작 전 `.claude/settings.json`, MCP 설정, 스킬 파일 자동 스캔
- 신뢰할 수 없는 구성 요소 발견 시 스프린트 시작 차단

### 3. Toxic Data Flow 분석
- eval_dispatch.py가 외부 모델에 코드 전송 시 민감 데이터 흐름 추적
- API 키, 비밀번호가 평가 프롬프트에 포함되지 않도록 자동 마스킹

---

## AHOY 개선 제안 Top 3

### 1. 스프린트 시작 전 보안 프리스캔 (Security Pre-scan)
- **현재**: 스프린트가 보안 검증 없이 시작됨
- **개선**: planned→contracted 전이 시 프로젝트 보안 상태 자동 스캔
- **구현 방향**:
  - `security_prescan.py` 신규 모듈
  - `.claude/settings.json` Hook 설정 무결성 확인
  - MCP 서버 도구 정의 스냅샷 저장 + 변조 감지
  - `.env`, credentials 파일 존재 시 경고 + eval_dispatch.py 마스킹 규칙 자동 생성
  - PreToolUse Hook에서 스프린트 시작 시 자동 실행

### 2. Tool Shadowing 방어 Hook
- **현재**: MCP 도구 호출에 대한 보안 검증 없음
- **개선**: MCP 도구가 다른 도구를 가로채는 섀도잉 공격 감지
- **구현 방향**:
  - `hooks/mcp_integrity_hook.sh` — PreToolUse에서 MCP 도구 이름/설명 해시 검증
  - 최초 등록 시 `trusted_tools.json` 스냅샷 생성
  - 도구 정의 변경 감지 시 하드 차단 + 관리자 알림
  - contract.md에 `allowed_mcp_tools` 섹션 추가

### 3. 평가 데이터 흐름 보안 (Toxic Flow Prevention)
- **현재**: eval_dispatch.py가 코드를 외부 모델(Codex/Gemini)에 전송 시 민감 데이터 검사 없음
- **개선**: 평가 전 자동 민감 데이터 마스킹
- **구현 방향**:
  - `eval_dispatch.py`에 `sanitize_for_eval()` 함수 추가
  - 정규식 기반 API 키/비밀번호/연결 문자열 탐지 + `[REDACTED]` 치환
  - 마스킹 맵 보존 → 평가 결과에서 원본 위치 역매핑
  - 마스킹 통계를 스프린트 로그에 기록
