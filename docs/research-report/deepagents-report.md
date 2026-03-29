# Deep Agents (LangChain) 분석 리포트

> 분석일: 2026-03-28 (10차)

## 기본 정보

| 항목 | 내용 |
|------|------|
| 프로젝트명 | Deep Agents |
| GitHub URL | https://github.com/langchain-ai/deepagents |
| 스타 | 17,700+ |
| 포크 | 2,500+ |
| 최근 커밋 | 2026년 3월 (매우 활발) |
| 라이선스 | MIT |
| 언어 | Python |

## 핵심 아키텍처

### 개요
Deep Agents는 LangChain과 LangGraph 위에 구축된 에이전트 하네스로, 계획 도구, 파일시스템 백엔드, 서브에이전트 스폰 기능을 갖추고 있다. 2026년 3월 LangChain이 공식 출시한 "구조화된 런타임"으로 주목받았다.

### 구조
```
[사용자 요청] → [Main Agent (Planning + Execution)]
                      ├── write_todos (계획 도구)
                      ├── Filesystem Tools (read/write/edit/ls/glob/grep)
                      ├── execute (Shell + Sandboxing)
                      ├── task (서브에이전트 스폰)
                      └── Context Management
                            ├── Auto-summarization
                            └── Large output → file 저장
```

### 핵심 특징

1. **write_todos 계획 도구**: 에이전트가 자체적으로 할 일 목록을 관리하며 진행 추적
2. **서브에이전트 스폰 (task tool)**: 컨텍스트 격리된 전문 서브에이전트를 동적 생성
3. **자동 컨텍스트 관리**: 큰 출력을 파일로 자동 저장, 컨텍스트 요약으로 토큰 절약
4. **파일시스템 네이티브**: read_file, write_file, edit_file, ls, glob, grep 내장
5. **LangGraph 런타임**: 내구성 있는 실행, 스트리밍, human-in-the-loop
6. **프로바이더 무관**: 도구 호출을 지원하는 모든 LLM과 호환
7. **100% 오픈소스 (MIT)**: 완전한 확장성
8. **JS 버전 동시 제공**: deepagentsjs로 Node.js 생태계 지원

## AHOY와 비교

### AHOY보다 나은 점

1. **서브에이전트 컨텍스트 격리**: task 도구로 서브에이전트를 스폰하면 메인 에이전트 컨텍스트를 오염시키지 않음. AHOY는 단일 Generator 세션 내 실행
2. **자동 컨텍스트 요약**: 대형 출력물을 자동으로 파일 저장 + 요약으로 토큰 절약. AHOY는 handoff 시에만 컨텍스트 관리
3. **동적 계획 수정**: write_todos로 실행 중 계획을 실시간 수정. AHOY는 contract.md가 스프린트 동안 고정
4. **풍부한 생태계**: LangChain/LangGraph/LangSmith 통합, 프로바이더 무관. AHOY는 Claude + Codex/Gemini에 한정
5. **내장 파일시스템 도구**: glob, grep 등 코드베이스 탐색 도구 내장. AHOY는 Claude Code의 도구에 의존
6. **대규모 커뮤니티**: 17.7k 스타, LangChain 공식 프로젝트

### AHOY가 더 나은 점

1. **Generator-Evaluator 분리**: Deep Agents는 자기 자신이 생성하고 자기 자신이 판단. 자기평가 편향 위험
2. **다중 모델 컨센서스**: Deep Agents는 단일 모델. AHOY는 최소 2개 외부 모델 합의
3. **Hook 기반 하드 차단**: Deep Agents는 소프트 가드레일. AHOY는 PreToolUse/PostToolUse로 하드 차단
4. **파일 소유권 분리**: Deep Agents는 에이전트가 모든 파일 자유 접근
5. **Generator 의견 strip**: Deep Agents에는 의견 필터링 없음
6. **스프린트 상태머신**: Deep Agents는 자유형 실행. AHOY는 엄격한 상태 전이
7. **rework 제한**: Deep Agents는 무한 반복 가능. AHOY는 최대 3회로 제한
8. **계약 기반 개발**: Deep Agents는 자유형 목표. AHOY는 contract.md 명세

## 배울 만한 구체적 아이디어

### 1. 서브에이전트 기반 평가 격리
```python
# eval_dispatch.py에서 서브에이전트 패턴 적용
async def evaluate_with_isolation(code, contract):
    """각 평가자를 격리된 서브에이전트로 실행"""
    codex_task = spawn_subagent(
        model="codex",
        context={"code": code, "contract": contract},
        isolation="full"  # 메인 컨텍스트와 완전 분리
    )
    gemini_task = spawn_subagent(
        model="gemini",
        context={"code": code, "contract": contract},
        isolation="full"
    )
    return await asyncio.gather(codex_task, gemini_task)
```

### 2. 자동 컨텍스트 요약 for Handoff
```python
# handoff 생성 시 자동 요약
def create_handoff(sprint_context):
    if token_count(sprint_context) > MAX_HANDOFF_TOKENS:
        summary = llm.summarize(sprint_context, max_tokens=2000)
        save_full_context_to_file(sprint_context)
        return summary + "\n\n[전체 컨텍스트: .ahoy/context/{sprint_id}.md]"
    return sprint_context
```

### 3. 실행 중 동적 계획 수정 (Adaptive Contract)
- contract.md의 요구사항 중 평가 통과한 항목을 자동 마킹
- rework 시 미통과 항목만 집중하는 동적 계획

---

## AHOY 개선 제안 Top 3

### 1. 평가자 서브에이전트 격리 패턴
- **파일**: `eval_dispatch.py`
- **변경**: 각 평가자(Codex, Gemini) 호출을 독립 컨텍스트로 격리. 이전 평가자의 결과가 다음 평가자에 영향 못 미치도록 완전 병렬 격리 실행
- **효과**: 평가자 간 오염 방지, 독립성 강화

### 2. 스프린트 컨텍스트 자동 요약 시스템
- **파일**: handoff 생성 로직
- **변경**: 스프린트 컨텍스트가 임계값(예: 50K 토큰) 초과 시 LLM으로 자동 요약 + 전체 컨텍스트를 파일로 보존. handoff에는 요약만 포함
- **효과**: handoff 토큰 비용 50-70% 절감, 새 세션 로딩 속도 향상

### 3. 동적 계획 수정 (Adaptive Contract)
- **파일**: `contract.md` 관리 로직, Hook
- **변경**: 평가 통과한 요구사항은 자동 `[PASSED]` 마킹. rework 시 Generator에게 미통과 항목만 집중하도록 지시. 토큰 절약 + rework 효율 향상
- **효과**: rework 시 불필요한 재생성 방지, 수렴 속도 향상
