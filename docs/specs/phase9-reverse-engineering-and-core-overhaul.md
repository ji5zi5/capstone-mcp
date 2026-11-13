# Specification: Native Reverse Engineering, Tool Surface Consolidation & IPC Integrity (Phase 9)

## 1. Problem Statement (문제 정의)

Phase 1부터 8까지의 기능 추가와 리팩터링을 거치면서, `capstone-mcp` 시스템은 정적 검사(524개 테스트 통과, 0 린트 에러)와 별개로 다음과 같은 심각한 아키텍처적 마찰과 실효성 한계에 봉착했습니다:

1. **도구 표면 과대 팽창 (66개 도구 난립)**:
   - 복합 도구(`capstone_manage_display`, `capstone_manage_graph`, `capstone_manage_instrument`)가 도입되었음에도, 35개의 하위 개별 도구와 8개의 저수준 좌표 클릭 매크로(`capstone_click`, `capstone_drag` 등)가 여전히 `@mcp.tool`로 병행 등록되어 있음.
   - MCP 클라이언트 접속 시 매 턴 15,000~20,000 토큰의 프롬프트 스키마를 낭비하고, LLM의 도구 선택 오류율을 증가시킴.

2. **IPC 진단 정보 유실 및 취약한 에러 추정**:
   - `src/capstone_mcp/automation_worker.py:63`의 `stderr=subprocess.DEVNULL` 설정으로 인해 자식 프로세스(`native_main.py`)의 C++ COM 충돌, 세그멘테이션 오류, 임포트 에러가 완전히 은폐됨.
   - `automation_models.py`의 `NativeReply` 모델이 예외를 단순 문자열(`error: str | None`)로만 전달하여, 부모 프로세스인 `server.py:891-940`에서 문자열 소문자 검색(`if "table" in lower:`)으로 에러 코드를 추측하는 취약한 구조를 가짐.

3. **도메인 혼란 및 비본질적 스코프 크립 (Tutor)**:
   - 전문 과학 데이터 수집 및 분석 서버에 70KB 분량의 고등학교 물리 퀴즈/과외 코드(`src/capstone_mcp/tutor/`, `tools/physics.py` 내 튜터 도구)가 기생하여 도구 수와 유지보수 부담을 가중시킴.
   - 실험 런(Run) 관리 도구(`rename_run`, `delete_run`, `set_run_visibility`)가 전용 `runs/` 패키지가 아닌 `tools/displays.py` 안에 잘못 배치되어 있음.

4. **네이티브 리버싱 부재 및 260개 가짜 Mock 자가당착**:
   - 단위 테스트의 95% 이상이 손으로 작성한 가짜 UI 트리(`Snapshot`)를 기반으로 하여 실제 Qt 기반 Capstone 위젯과의 런타임 상호작용을 보증하지 못함.
   - 기존에 작성된 `src/capstone_mcp/bridge.py`가 디버그 포트와 연결되는 코드를 갖고 있으나, 실물 환경에서 어디까지 제어가 가능한지(센서/측정값 외에 GUI 조작 대체 가능 여부) 실증 검증되지 않음.

---

## 2. Solution (해결 방안)

다음 5대 핵심 축으로 Phase 9 수술을 진행합니다:

1. **도구 표면 대숙청 (66개 → ~18개 수준 압축)**:
   - 이미 복합 도구로 완전히 대체 가능한 35개 개별 도구와 8개 저수준 OS 클릭 매크로의 `@mcp.tool` 등록을 해제함.
   - 복합 도구(`manage_display`, `manage_graph`, `manage_instrument`, `manage_run`, `manage_file`, `manage_analysis`) 및 핵심 고수준 분석 도구만 깔끔하게 노출함.

2. **IPC 에러 수집 및 전구간 구조화된 에러 계약 완비**:
   - `automation_worker.py`의 `stderr`를 `subprocess.PIPE`로 열고, 메모리 보호(4KB/line) 및 200줄 순환 링 버퍼(`collections.deque`)로 실시간 수집.
   - `NativeReply`에 `error_code: str | None`, `remediation: str | None` 필드를 추가하여 자식 프로세스의 구체적 예외가 `format_tool_error`까지 손실 없이 관통하도록 재설계.

3. **튜터 모듈 전량 퇴출 및 런(Run) 도메인 정상화**:
   - `src/capstone_mcp/tutor/` 및 튜터 도구 2개(`capstone_tutor_get_lesson`, `capstone_tutor_guide_step`)를 완전 삭제함.
   - `tools/physics.py`의 순수 과학 계산/피팅/플롯/보고서/매크로 도구는 온전히 보존함.
   - `rename_run`, `delete_run`, `set_run_visibility`를 `tools/displays.py`에서 떼어내어 `runs/` 도메인의 `capstone_manage_run` 복합 도구로 일원화함.

4. **Capstone 내부 인터페이스 정밀 리버싱 실사**:
   - `bridge.py`의 CDP WebSocket 연결을 실물 Capstone 런타임에서 직접 가동하여 실측치(지원 API, 응답 속도, 실패 모드)를 도출.
   - Capstone의 `SenseAndControl` 외에 다른 QWebChannel 객체(`ViewModelHandler`, `FileHandler`)의 실제 패킷 교환 메커니즘을 규명하고 GUI 대체 가능성의 한계를 명확히 측정.

5. **실물 스모크 테스트 분리 및 CI 가드레일**:
   - 단위 테스트는 순수 알고리즘/변환 위주로 슬림화.
   - 로컬 `Capstone.exe` 전용 E2E 스모크 테스트(`tests/test_live_smoke.py`)를 신설하여 `@pytest.mark.skipif(not HAS_CAPSTONE)` 가드로 헤드리스 CI와 로컬 실물 검증을 분리.

---

## 3. User Stories (사용자 스토리)

1. **AI 에이전트 사용자 관점**:
   - 복잡한 66개 도구 대신 명확한 ~18개의 정규화된 도구만 수신하여, 매 턴 토큰을 80% 이상 절감하고 도구 선택 결정장애를 겪지 않는다.
2. **개발자 및 유지보수자 관점**:
   - 자식 프로세스(`native_main.py`)가 충돌하거나 파이썬 예외가 발생할 때, `stderr` 순환 버퍼를 통해 완전한 스택 트레이스백을 실시간으로 확인하여 원인을 즉시 파악한다.
3. **MCP 클라이언트 관점**:
   - 모든 도구 실패 시 취약한 문자열 추정이 아닌, 자식 프로세스로부터 직접 전달된 일관된 구조화된 JSON 에러 코드(`error_code`)와 조치 방안(`remediation`)을 수신하여 자가 복구한다.
4. **과학 연구자 관점**:
   - 쓸데없는 고등학교 퀴즈 도구 없이, 고유한 OLS 선형 회귀, 플롯 렌더링, 수식 계산기, 실험 보고서 생성, Canonical 실험 매크로 기능을 안정적으로 사용한다.
5. **테스트/CI 엔지니어 관점**:
   - 허수아비 Mock에 갇히지 않고, 실제 로컬 Capstone과 연동되는 실물 스모크 테스트를 통해 실제 소프트웨어와의 호환성을 검증할 수 있다.

---

## 4. Implementation Decisions (상세 구현 결정)

### 4.1 도구 등록 해제 매트릭스
* **등록 해제 대상 개별 도구 (35개)**:
  - 디스플레이: `capstone_create_table`, `capstone_set_table_columns`, `capstone_read_table`, `capstone_create_digits`, `capstone_create_scope`, `capstone_set_scope_trigger`, `capstone_create_fft`, `capstone_read_fft_peaks`, `capstone_add_page`, `capstone_set_page_layout`.
  - 그래프: `capstone_create_graph`, `capstone_select_graph_measurement`, `capstone_observe_graph`, `capstone_graph_report`, `capstone_read_graph`, `capstone_fit_graph`, `capstone_set_graph_fits`, `capstone_analyze_graph`, `capstone_toggle_graph_statistics`, `capstone_measure_graph_area`, `capstone_graph_delta`.
  - 계측기: `capstone_recording_status`, `capstone_set_recording`, `capstone_step_sampling_rate`, `capstone_select_sensor`, `capstone_configure_sensor`, `capstone_repeat_acquisition`, `capstone_zero_sensor`, `capstone_set_signal_generator`, `capstone_read_signal_generator_status`, `capstone_set_recording_condition`, `capstone_set_sampling_mode`, `capstone_keep_sample`, `capstone_scan_wireless_sensors`, `capstone_connect_wireless_sensor`, `capstone_calibrate_sensor`.
* **등록 해제 대상 저수준 매크로 (8개)**:
  - `capstone_click`, `capstone_drag`, `capstone_scroll`, `capstone_keys`, `capstone_type_text`, `capstone_read_value`, `capstone_set_value`, `capstone_action`.
* **삭제 대상 튜터 도구 (2개)**:
  - `capstone_tutor_get_lesson`, `capstone_tutor_guide_step`.
* **최종 유지 도구 (~18개)**:
  - 세션: `capstone_attach`, `capstone_windows`, `capstone_snapshot`, `capstone_screenshot`.
  - 복합 관리: `capstone_manage_display`, `capstone_manage_graph`, `capstone_manage_instrument`, `capstone_manage_run`.
  - 파일 I/O: `capstone_save_experiment`, `capstone_open_experiment`, `capstone_export_data`, `capstone_inspect_file`, `capstone_extract_dataset`.
  - 과학 분석: `capstone_linear_fit`, `capstone_plot`, `capstone_compare_runs`, `capstone_create_calculation`, `capstone_generate_lab_report`, `capstone_run_experiment_macro`.

### 4.2 IPC `stderr` 안전 버퍼링 파이프라인
* `src/capstone_mcp/automation_worker.py`:
  - `self.stderr_buffer = collections.deque(maxlen=200)`
  - 비동기 데몬 스레드에서 `iter(lambda: process.stderr.readline(4096), '')` 수집.
  - 프로세스 비정상 종료 시 버퍼 잔류 문자열을 취합하여 예외 발생.
  - `reset()` 호출 시 `self.stderr_buffer.clear()` 수행.

### 4.3 IPC 전구간 구조화된 에러 계약
* `src/capstone_mcp/automation_models.py`:
  ```python
  class NativeReply(Model):
      identifier: str
      result: JsonValue = None
      error: str | None = None
      error_code: str | None = None
      remediation: str | None = None
      graph_failure: GraphFailure | None = None
  ```
* `src/capstone_mcp/native_loop.py`:
  - 각 도메인 예외 발생 시 사전 정의된 `error_code`와 `remediation`을 `NativeReply`에 주입.
* `src/capstone_mcp/server.py`:
  - `format_tool_error`에서 문자열 휴리스틱 매칭 대신 `reply.error_code`와 `reply.remediation`을 최우선으로 사용하여 `ToolErrorPayload` 생성.

### 4.4 튜터 모듈 삭제
* 디렉터리 `src/capstone_mcp/tutor/` 전량 삭제.
* `src/capstone_mcp/tools/physics.py`에서 튜터 관련 임포트 및 도구 정의 제거.
* `tests/test_tutor.py` 및 관련 튜터 테스트 삭제.

### 4.5 런(Run) 관리 도메인 일원화
* `src/capstone_mcp/runs/`에 `manage_run` 복합 도구 로직 구현.
* `tools/displays.py`에서 `rename_run`, `delete_run`, `set_run_visibility` 제거 및 `capstone_manage_run` 등록.

### 4.6 리버싱 실사 계획 (Reverse Engineering Investigation)
* **목표 1 (CDP 가동 실측)**: 로컬 `Capstone.exe`를 구동하고, `bridge.py`의 `discover_target()`과 `evaluate()`가 실제 응답을 반환하는지 속도(ms)와 성공률 측정.
* **목표 2 (QWebChannel 패킷 관측)**: `capstonelibrary.js`의 `ViewModelHandler`(-1, -2) 및 `FileHandler`(-5, -6, -7, -8) 호출이 실제 Capstone C++ 엔진에서 유효하게 수신/처리되는지 WebSocket 레벨에서 패킷 교환 시험.
* **목표 3 (GUI 대체 경계 확정)**: 실측 결과를 바탕으로 "어디까지 WebChannel로 대체할 수 있고, 어디부터 UIA 매크로가 필수적인가"의 기술적 경계선 확정.

---

## 5. Verification Plan (검증 계획)

1. **계약 테스트 (Contract Tests)**:
   - `tests/test_server_contract.py`에 등록된 도구 수가 22개 이하인지 검증하는 테스트 추가 (`assert len(mcp.list_tools()) <= 22`).
2. **`stderr` 수집 단위 테스트**:
   - `tests/test_worker_stderr.py`를 신설하여 자식 프로세스가 고의로 크래시를 낼 때 최근 200줄의 에러가 누락 없이 부모로 전달되는지 확인.
3. **IPC 구조화된 에러 전송 단위 테스트**:
   - 자식 프로세스에서 발생한 커스텀 에러 코드가 `NativeReply`를 통해 `server.py`까지 손실 없이 전달되는지 확인.
4. **로컬 실물 스모크 테스트 (`tests/test_live_smoke.py`)**:
   - `HAS_CAPSTONE = Path(r"C:\Program Files\PASCO Scientific\Capstone\Capstone.exe").exists()` 조건 하에서 윈도우 연결, 스냅샷, 디버그 포트 통신 성공 여부 검증.
5. **기존 회귀 테스트 통과**:
   - `uv run --no-sync ruff check src tests`
   - `uv run --no-sync basedpyright src`
   - `uv run --no-sync pytest` (500+ 단위 테스트 무결성 보장)
