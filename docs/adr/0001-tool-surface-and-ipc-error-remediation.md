# ADR 0001: 도구 표면 축소, IPC 에러 파이프라인 정규화 및 튜터 모듈 퇴출

- **상태 (Status)**: 승인됨 (Accepted)
- **일자 (Date)**: 2026-11-13
- **결정권자 (Deciders)**: 사용자, 에이전트

## 맥락 (Context)
1. FastMCP에 등록된 도구 수가 66개로 과도하게 팽창하여 매 턴 15,000~20,000 토큰의 프롬프트 비용을 소모하고 LLM 도구 선택 오류를 유발하고 있었음.
2. `capstone_manage_display`, `capstone_manage_graph`, `capstone_manage_instrument` 등 복합 도구가 도입되었음에도 35개의 레거시 개별 도구와 8개의 저수준 OS 좌표 클릭 매크로가 병행 노출되고 있었음.
3. `automation_worker.py:63`의 `stderr=subprocess.DEVNULL` 설정으로 자식 프로세스의 C++ 충돌 및 파이썬 트레이스백이 완전 은폐되고 있었음.
4. `automation_models.py`의 `NativeReply` 모델이 에러를 `str | None`으로만 전달하여 `server.py`에서 취약한 문자열 부분 일치(`if "table" in lower:`)로 에러 코드를 추정하고 있었음.
5. `src/capstone_mcp/tutor/` 및 `tools/physics.py` 내의 튜터 퀴즈 기능이 전문 과학 계측 도메인과 섞여 유지보수 부담을 가중시키고 있었음.

## 결정 (Decision)
1. **도구 표면 축소**:
   - 복합 도구(`manage_display`, `manage_graph`, `manage_instrument`)의 하위 액션으로 100% 매핑되는 35개 개별 도구의 `@mcp.tool` 등록을 해제함.
   - `server.py`의 저수준 마우스/키보드 클릭 도구 8개(`click`, `drag`, `scroll`, `keys`, `type_text` 등)의 `@mcp.tool` 등록을 해제하고 내부 전용 함수로 격리함.
   - 외부 노출 도구 수를 ~20개 수준으로 압축함.
2. **`stderr` 버퍼링 파이프라인 구축**:
   - `stderr=subprocess.PIPE`로 열고 데몬 스레드에서 비동기 수집함.
   - 한 줄당 4,096바이트 길이 제한(`readline(4096)`)을 두어 메모리 고갈을 방지하고, 최근 200줄을 `collections.deque(maxlen=200)` 순환 버퍼에 보관함.
   - 자식 프로세스 크래시 시 버퍼의 트레이스백을 추출하여 에러 메시지에 첨부하며, 세션 `reset()` 시 버퍼를 초기화하여 로그 혼선을 방지함.
3. **IPC 전구간 구조화된 에러 계약 확장**:
   - `NativeReply` 모델에 `error_code: str | None`, `remediation: str | None` 필드를 추가함.
   - `native_loop.py`의 에러 응답부터 부모 프로세스 및 `server.py:format_tool_error`까지 구조화된 에러 정보가 손실 없이 관통하도록 리팩터링함.
4. **튜터 모듈 전량 퇴출**:
   - `tools/physics.py` 내의 수치 회귀(`linear_fit`), 산점도 플롯(`plot`), 계산식 생성(`create_calculation`), 실험 보고서 작성(`generate_lab_report`), 실험 매크로(`run_experiment_macro`)는 핵심 기능으로 온전히 보존함.
   - 순수 교육용 퀴즈 모듈인 `src/capstone_mcp/tutor/` 및 `capstone_tutor_get_lesson`, `capstone_tutor_guide_step` 도구는 전량 삭제함.

## 결과 및 영향 (Consequences)
- **긍정적 효과**: 프롬프트 토큰 소모 대폭 절감, 자식 프로세스 크래시 디버깅 가시성 확보, 에러 오분류 원천 차단, 코드베이스 응집도 향상.
- **부정적/주의 효과**: 개별 도구를 직접 호출하던 외부 클라이언트나 기존 테스트 코드는 복합 도구 호출 방식으로 갱신되어야 함.
