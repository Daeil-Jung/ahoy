# Rulebricks Claude Code Guardrails 분석 리포트

> 분석일: 2026-03-28 (3차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Claude Code Guardrails (by Rulebricks) |
| GitHub URL | https://github.com/rulebricks/claude-code-guardrails |
| 스타 | 62 |
| 최근 커밋 | 2026-01-15 |
| 라이선스 | MIT |
| 언어 | Python (64.7%), Shell (35.3%) |
| 후속 프로젝트 | stoplight.ai (오픈소스 예정) |

## 핵심 아키텍처

### 클라우드 기반 Hook 파이프라인

```
Claude Code → PreToolUse Hook → Rulebricks API → allow / deny / ask
                                     ↑
                            Visual Rule Editor (웹 UI)
```

### 3가지 규칙 템플릿

| 템플릿 | 용도 |
|--------|------|
| Bash Command Guardrails | 셸 명령 실행 제어 |
| File Access Policy | 읽기/쓰기/편집 작업 제한 |
| MCP Tool Governance | MCP 서버 호출 관리 |

### 주요 파일

| 파일 | 용도 |
|------|------|
| `guardrail.py` | PreToolUse hook 구현 |
| `install.sh` | 자동 설치 스크립트 |
| `~/.claude/settings.json` | 환경 변수 설정 |

## 핵심 특성

### 비주얼 규칙 에디터
- 코드가 아닌 **Decision Table** 형식으로 규칙 정의
- 비개발자도 규칙 수정 가능
- 조건부 로직 지원 (예: `rm -rf`는 `node_modules`에서만 허용)

### 실시간 업데이트
- 규칙 변경 시 재시작/재배포 불필요
- 모든 Claude Code 세션에 즉시 전파

### 감사 로그
- 모든 allow/deny/ask 결정을 로깅
- 검색 가능한 감사 추적
- 도구 유형, 승인 결정, 빈도 분석
- 민감 데이터 전송 전 자동 삭제 옵션

### 프라이빗 인프라
- 자체 서버 배포 가능
- 기업 환경 적용 가능

## AHOY 대비 비교

### Rulebricks가 AHOY보다 나은 점

1. **비주얼 규칙 에디터**: Decision Table로 비개발자도 규칙 관리 가능. AHOY의 hook은 코드 수준 수정 필요
2. **실시간 규칙 업데이트**: 재시작 없이 즉시 적용. AHOY는 hook 변경 시 세션 재시작 필요
3. **중앙집중 감사 로그**: 모든 tool call 결정을 검색 가능한 형태로 로깅. AHOY는 평가 결과만 기록
4. **팀 전체 일관된 규칙 적용**: 클라우드 기반으로 팀 전체에 동일 규칙 자동 전파
5. **MCP Tool Governance**: MCP 서버 호출까지 가드레일 적용. AHOY는 내장 도구만 관리

### AHOY가 Rulebricks보다 나은 점

1. **Generator-Evaluator 분리**: Rulebricks는 단순 allow/deny 결정. 코드 품질 평가 기능 없음
2. **다중 모델 컨센서스**: 없음. 단일 규칙 엔진 기반 결정
3. **스프린트 상태머신**: 없음. 개별 tool call 수준의 게이팅만 제공
4. **코드 품질 평가**: 없음. 보안/접근 제어에 특화
5. **Generator 의견 strip**: 해당 없음 (평가 기능 자체가 없음)
6. **계약 기반 개발**: 없음. 워크플로우 관리 기능 없음
7. **외부 API 의존**: Rulebricks API가 다운되면 hook 동작 불가. AHOY는 로컬 실행

### 배울 만한 구체적 아이디어

1. **비주얼 규칙 에디터 패턴 → Hook 규칙 YAML 외부화**
   - hook 규칙을 코드에서 분리하여 YAML/JSON으로 정의
   - 비개발자도 수정 가능한 형태로 외부화
   - 기존 제안 "선언적 Hook 규칙 DSL"의 구체적 참조

2. **중앙집중 감사 로그 → SQLite 감사 로그**
   - 모든 hook 결정 (allow/deny)을 SQLite에 기록
   - 검색/분석 가능한 감사 추적
   - 기존 제안 "SQLite 평가 감사 로그"와 결합

3. **실시간 규칙 핫 리로드**
   - hook 설정 파일의 변경 감지 (file watcher)
   - 세션 재시작 없이 규칙 즉시 적용

---

## AHOY 개선 제안 Top 3

### 1. Hook 규칙 핫 리로드
- **구현 대상**: hook 로더 시스템
- **변경 내용**: hook 설정 파일(YAML/JSON)의 변경을 감지하여 세션 재시작 없이 규칙 즉시 적용. `watchdog` 라이브러리 또는 파일 mtime 체크로 구현
- **효과**: 스프린트 중 규칙 조정 시 워크플로우 중단 없음
- **참조**: Rulebricks 실시간 업데이트

### 2. Tool Call 감사 로그 통합
- **구현 대상**: hook 시스템 + SQLite
- **변경 내용**: PreToolUse/PostToolUse hook에서 모든 tool call을 `audit_log.sqlite`에 기록 (시간, 도구, 결정, 이유). 기존 제안 "SQLite 평가 감사 로그"를 확장하여 평가뿐 아니라 모든 tool call 포함
- **효과**: 스프린트 전체 활동의 완전한 추적 가능. handoff 문서 품질 향상
- **참조**: Rulebricks Audit Log, Overstory SQLite

### 3. MCP Tool 가드레일 확장
- **구현 대상**: `hooks/pre_tool_use/` (MCP call 인터셉트)
- **변경 내용**: MCP 서버 호출을 가드레일 대상에 포함. contract.md에 허용된 MCP 도구 목록 명시, 미허용 도구 호출 시 차단
- **효과**: 외부 도구 사용 범위를 계약에 기반하여 제한
- **참조**: Rulebricks MCP Tool Governance, OpenGuardrails MCP 보호
