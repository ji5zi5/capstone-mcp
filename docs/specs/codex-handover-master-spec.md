# 📘 Codex Master Handover & Codebase Overhaul Specification

**Document Version**: 1.0.0 (Master Handoff)  
**Target Repository**: `capstone-mcp` (`main` branch)  
**Target Engineer/Agent**: OpenAI Codex & Senior Systems Engineers  
**Date**: 2026-11-13  
**Current State**: 524 tests passing (1 skipped), Ruff & Basedpyright clean, GitHub Actions CI green (`completed: success`).

---

## 1. Executive Autopsy & Mission Mandate (총괄 부검 및 사명)

### 1.1 현상의 진실 (The Illusion vs. The Truth)
현재 `capstone-mcp` 저장소는 정적 지표상 완벽해 보이지만, 아키텍처적으로는 **자가당착적 모킹(Mocking Tautology) 위에 세워진 66개 도구의 인디렉션 모래성**입니다.

1. **도구 표면 팽창 (66 Tools)**: FastMCP에 66개의 도구가 전면 노출되어 매 턴 15,000~20,000 토큰을 낭비하고 LLM의 도구 선택 오류를 유발합니다.
2. **모킹 자가당착 (260+ MagicMock)**: 22개 테스트 파일이 실제 Capstone 창 대신 손으로 작성한 가짜 UI 트리(`Snapshot(controls=[...])`)만을 검증합니다. 실제 Qt/C++ 기반 Capstone 위젯이 UIA에 셀을 노출하지 않으면 실제 환경에서는 작동하지 않습니다.
3. **에러 은폐 IPC**: 단일 마우스 클릭이 부모 FastMCP와 자식 `native_main.py` 간 22단계 직렬화 파이프라인을 거치며, `automation_worker.py:63`의 `stderr=subprocess.DEVNULL` 설정으로 자식 프로세스의 C++ 충돌과 파이썬 예외가 완전히 은폐됩니다.
4. **문자열 눈치보기식 에러 분류**: `server.py:891-940`에서 예외 메시지의 소문자 부분 문자열(`if "table" in lower: DISPLAY_ERROR`)로 에러 코드를 추측하고 있습니다.
5. **스코프 크립**: 순수 측정 장비 MCP 서버에 70KB 분량의 물리 퀴즈/과외 모듈(`src/capstone_mcp/tutor/`, `tools/physics.py`)이 기생하고 있습니다.

### 1.2 핵심 사명 (The Mission)
Codex의 과업은 단순한 리팩터링이 아니라 다음 **4대 수술**을 완수하는 것입니다:
1. **도구 표면 대숙청**: 66개 도구를 **단 6개의 정규화된 복합 관리 도구**로 압축.
2. **파이프라인 정상화**: `stderr=DEVNULL` 제거, 자식 프로세스 트레이스백 순환 버퍼 도입, 정규화된 `CapstoneError` 계층 구축.
3. **잡동사니 제거**: `tutor/` 및 `tools/physics.py` 전량 삭제 (Deletion Test 통과).
4. **Phase 9 네이티브 리버싱 구현**: `pywinauto` 마우스 클릭을 걷어내고, Capstone 내부에 이미 존재하는 **QtWebEngine / QWebChannel JSON-RPC 브리지**를 통한 무(無)GUI 고속 백그라운드 통신 채널 구축.

---

## 2. 전체 아키텍처 비교 (Current vs. Target Architecture)

```mermaid
flowchart TD
    subgraph Current ["현재 아키텍처 (22-Step Brittle IPC)"]
        LLM1["AI Agent / LLM"] -->|66개 도구 스키마| FastMCP1["FastMCP (server.py)"]
        FastMCP1 --> Worker["AutomationWorker (부모 프로세스)"]
        Worker -->|stdin JSON (stderr 은폐)| Subproc["native_main.py (자식 프로세스)"]
        Subproc --> Loop["native_loop.py"]
        Loop --> DisplayMgr["displays/ & instruments/"]
        DisplayMgr --> PyWinAuto["pywinauto / Windows UIA 매크로"]
        PyWinAuto -.->|불안정한 좌표 클릭| CapstoneUI["실제 PASCO Capstone GUI 창"]
    end

    subgraph Target ["목표 아키텍처 (Native Direct Bridge)"]
        LLM2["AI Agent / LLM"] -->|6개 복합 도구 스키마| FastMCP2["FastMCP (server.py)"]
        FastMCP2 --> CoreEngine["Capstone Engine Core"]
        CoreEngine --> NativeBridge["Native QWebChannel / DevTools Client"]
        NativeBridge ===|WebSocket / JSON-RPC 2.0| CapstoneNative["Capstone.exe 내부 C++ ViewModelHandler"]
        CoreEngine --> CapEngine["capfiles/ (순수 바이너리 파서)"]
    end
```

---

## 3. 도구 인벤토리 및 6대 복합 도구 통폐합 매트릭스

현재 등록된 66개 도구를 분석하여 삭제할 60개 레거시 도구와 유지/강화할 6대 복합 도구의 매핑을 정의합니다.

### 3.1 6대 목표 복합 도구 (Target Compound Tools)
모든 도구는 Pydantic `BaseModel` 기반의 단일 요청 객체(Request Envelope)를 수신합니다.

| 도구명 | 처리 영역 | 통합 대상 레거시 도구 |
|---|---|---|
| **`capstone_manage_display`** | 테이블, 디지트, 스코프, FFT, 페이지 레이아웃 | `create_table`, `read_table`, `set_table_columns`, `create_digits`, `create_scope`, `set_scope_trigger`, `create_fft`, `read_fft_peaks`, `add_page`, `set_page_layout` |
| **`capstone_manage_graph`** | 그래프 축, 커브, 좌표, 플롯 관측, 영역/델타 측정 | `create_graph`, `select_graph_measurement`, `observe_graph`, `read_graph`, `graph_report`, `graph_delta`, `measure_graph_area`, `toggle_graph_statistics` |
| **`capstone_manage_instrument`** | 센서 설정, 0점 조절, 신호발생기, 샘플링 모드, 레코딩 | `recording_status`, `set_recording`, `step_sampling_rate`, `select_sensor`, `configure_sensor`, `zero_sensor`, `set_signal_generator`, `read_signal_generator_status`, `scan_wireless_sensors`, `connect_wireless_sensor`, `calibrate_sensor` |
| **`capstone_manage_run`** | 실험 런 관리, 이름 변경, 삭제, 가시성 토글 | `rename_run`, `delete_run`, `set_run_visibility` (기존 `tools/displays.py`에서 탈출) |
| **`capstone_manage_file`** | 파일 열기, 저장, 내보내기, 바이너리 파싱, 데이터셋 추출 | `save_experiment`, `open_experiment`, `export_data`, `csv_page`, `inspect_file`, `file_datasets`, `extract_dataset`, `fit_file`, `compare_file` |
| **`capstone_manage_analysis`** | 수치해석, 통계, 커브 피팅, 선형 회귀 | `linear_fit`, `fit_graph`, `fit_models`, `set_graph_fits`, `analyze_graph` |

### 3.2 삭제 대상 저수준/잡동사니 도구 (즉시 삭제)
* **저수준 UI 매크로 (`server.py`)**: `capstone_click`, `capstone_drag`, `capstone_scroll`, `capstone_keys`, `capstone_type_text`, `capstone_snapshot`, `capstone_action`, `capstone_read_value`, `capstone_set_value`.
* **물리 퀴즈/과외 도구 (`tools/physics.py`)**: `capstone_guide`, `capstone_plot`, `capstone_create_calculation`, `capstone_generate_lab_report`, `capstone_tutor_get_lesson`, `capstone_tutor_guide_step`, `capstone_run_experiment_macro`.

### 3.3 계약 테스트 추가 (`tests/test_server_contract.py`)
Codex는 구현 전 반드시 다음 테스트를 작성하여 실패(Red)를 확인해야 합니다:
```python
def test_fastmcp_tool_surface_ceiling():
    """Ensure FastMCP tool surface remains compact (<= 12 tools)."""
    tools = mcp.list_tools()
    assert len(tools) <= 12, (
        f"Tool bloat detected! Found {len(tools)} tools. "
        "Consolidate into compound management tools."
    )
```

---

## 4. IPC 서브프로세스 및 에러 은폐 결함 수술

### 4.1 문제 위치: `src/capstone_mcp/automation_worker.py:61-65`
```python
# [현재 코드 - 에러 은폐]
def _spawn(self) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-X", "utf8", "-u", "-m", "capstone_mcp.native_main"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, # 치명적!
        text=True, encoding="utf-8",
    )
```

### 4.2 개선 구현 명세
1. `stderr=subprocess.PIPE`로 변경.
2. 별도의 백그라운드 스레드에서 `stderr` 라인을 비동기 수신하여 `collections.deque(maxlen=200)` 순환 링 버퍼에 보관.
3. 자식 프로세스가 비정상 종료(`process.poll() is not None` 또는 `BrokenPipeError`)하거나 타임아웃 발생 시, 링 버퍼에 저장된 마지막 200줄의 트레이스백을 추출하여 `NativeProcessCrashError` 예외에 탑재.

```python
# [목표 구현 가이드]
class AutomationWorker:
    def __init__(self, ...):
        self.stderr_buffer: collections.deque[str] = collections.deque(maxlen=200)
        self.stderr_reader_thread: Thread | None = None

    def _start_stderr_drain(self, process: subprocess.Popen[str]) -> None:
        def drain():
            if process.stderr is None:
                return
            for line in iter(process.stderr.readline, ''):
                self.stderr_buffer.append(line)
        self.stderr_reader_thread = Thread(target=drain, daemon=True)
        self.stderr_reader_thread.start()
```

---

## 5. 정규화된 예외 아키텍처 (`CapstoneError`)

### 5.1 문제 위치: `src/capstone_mcp/server.py:891-940`
```python
# [현재 코드 - 취약한 문자열 부분 일치]
lower = cleaned.lower()
if "attach" in lower or "session" in lower:
    code = "SESSION_NOT_ATTACHED"
elif "graph" in lower:
    code = "GRAPH_OPERATION_ERROR"
elif "table" in lower or "digits" in lower:
    code = "DISPLAY_ERROR"
```

### 5.2 구조화된 예외 계층 정의 (`src/capstone_mcp/errors.py`)
```python
class CapstoneError(Exception):
    def __init__(self, error_code: str, message: str, remediation: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.remediation = remediation

    def to_payload(self) -> ToolErrorPayload:
        return ToolErrorPayload(
            error_code=self.error_code,
            message=self.message,
            remediation=self.remediation,
        )

class SessionNotAttachedError(CapstoneError): ...
class DisplayNotFoundError(CapstoneError): ...
class GraphOperationError(CapstoneError): ...
class InstrumentCommunicationError(CapstoneError): ...
class NativeProcessCrashError(CapstoneError): ...
```
`format_tool_error`는 문자열 정규식이 아닌, 발생한 예외 객체의 인스턴스 타입(`isinstance(err, CapstoneError)`)을 기반으로 직접 직렬화하도록 전면 재작성합니다.

---

## 6. 제거 대상 파일 및 스코프 크립 전수 목록

다음 디렉터리와 파일들은 저장소 정체성에 부합하지 않으므로 즉시 삭제합니다:

```text
[삭제 목록]
src/capstone_mcp/tutor/curriculum.py
src/capstone_mcp/tutor/lesson_generator.py
src/capstone_mcp/tutor/manual_extractor.py
src/capstone_mcp/tutor/workspace_sync.py
src/capstone_mcp/tutor/__init__.py
src/capstone_mcp/tools/physics.py
tests/test_tutor.py
tests/test_physics_tools.py
tests/test_curriculum.py
```
*삭제 후 `src/capstone_mcp/server.py`의 `mcp.include_router(physics.router)` 및 튜터 리소스 등록 라인을 함께 제거합니다.*

---

## 7. 260+ MagicMock 감사 및 실물 검증 전략

### 7.1 MagicMock 집중 분포 파일 (22개)
* `test_signal_generator.py` (30개)
* `test_oscilloscope_fft.py` (28개)
* `test_wireless_calibration.py` (21개)
* `test_display_harness.py` (20개)
* `test_smart_triggers.py` (19개)
* `test_run_visibility.py` (18개)
* `test_graphs.py` (15개)
* `test_calculator.py` (14개)
* `test_workbook_layout.py` (14개)
* `test_instruments.py` (13개)
* `test_table_display.py` (10개)

### 7.2 검증 전략 전환
1. **Mock 축소**: 단위 테스트에서 200줄씩 손으로 작성된 가짜 `Snapshot`을 최소화하고, 순수 비즈니스 로직(데이터 변환, 수치 계산)과 UI 통신 경계를 엄격히 분리.
2. **실물 스모크 테스트 구축 (`tests/test_live_smoke.py`)**:
   - `C:\Program Files\PASCO Scientific\Capstone\Capstone.exe`가 로컬에 존재할 때만 실행되는 E2E 스모크 테스트 구현:
     ```python
     @pytest.mark.skipif(
         not Path(r"C:\Program Files\PASCO Scientific\Capstone\Capstone.exe").exists(),
         reason="Live PASCO Capstone installation required",
     )
     def test_live_capstone_session_attach():
         ...
     ```

---

## 8. Phase 9: 네이티브 Capstone 리버스 엔지니어링 청사진 (핵심 발견)

> [!IMPORTANT]
> **실제 Capstone 내부 구조 분석 결과 (2026-11-13 규명)**:  
> Capstone은 순수 네이티브 윈도우 UI가 아닙니다. **Qt 5.15 기반의 C++ 코어와 내부 QtWebEngine(Chromium) 및 QtWebChannel**로 구성되어 있습니다.

### 8.1 발견된 바이너리 자산 (`C:\Program Files\PASCO Scientific\Capstone`)
1. **`Qt5WebChannel.dll` & `Qt5WebEngineCore.dll` (112MB)**:
   - Capstone 내부에 Chromium 엔진과 QWebChannel WebSocket 서버가 동작하고 있습니다.
2. **`Resources\www\javascripts\capstonelibrary.js` & `qwebchannel.js`**:
   - Capstone은 이미 내부에 **JSON-RPC 2.0 클라이언트/서버 통신 엔진**을 완벽하게 탑재하고 있습니다.

### 8.2 규명된 내부 JSON-RPC 2.0 프로토콜 명세
`capstonelibrary.js` 분석을 통해 밝혀진 실제 C++ 통신 패킷 구조:
```json
{
  "jsonrpc": "2.0",
  "object": "ViewModelHandler",
  "method": -2,
  "params": { ... },
  "id": "17314767220001",
  "sessionId": "system"
}
```

#### 식별된 C++ 핸들러 객체 및 메서드 ID:
1. **`ViewModelHandler` (객체명: `"ViewModelHandler"`)**:
   - `Method_CreateViewModel = -1`: 디스플레이 뷰모델 생성 (그래프, 테이블, 스코프)
   - `Method_ViewModelRequest = -2`: 뷰모델 데이터 요청 및 파라미터 조작
   - `Method_ViewModelRequestPromise = -3`: 비동기 요청 처리
2. **`FileHandler` (객체명: `"FileHandler"`)**:
   - `FileHandlerGetApplicationPaths = -5`: Capstone 설치 및 데이터 경로 획득
   - `FileHandlerReadImageDataBase64 = -6`: 이미지 데이터 Base64 읽기
   - `FileHandlerOpenFileChooser = -7`: 파일 선택창 호출
   - `FileHandlerCopy = -8`: 파일 복사 및 데이터 내보내기
3. **`window.javascriptBridge`**:
   - C++에서 QtWebChannel로 직접 노출된 브리지 객체:
     - `javascriptBridge.sendMessage(jsonString)`
     - `javascriptBridge.LanguageLoaded()`
     - `javascriptBridge.log(message)`

### 8.3 Phase 9 엔지니어링 구현 경로
Codex는 `pywinauto` 마우스 클릭을 걷어내고 다음 방식으로 네이티브 통신을 확립합니다:
1. **Chromium 원격 디버깅 포트 활성화**:
   - Capstone 실행 시 환경변수 `QTWEBENGINE_REMOTE_DEBUGGING=9222` 또는 명령줄 인수 `--remote-debugging-port=9222`를 부여하여 구동.
2. **WebSocket 직접 연결**:
   - 파이썬 `websockets` 라이브러리로 Capstone의 WebChannel 포트에 접속하여 `javascriptBridge`와 JSON-RPC 2.0 패킷을 직접 교환.
   - 마우스 클릭 없이 백그라운드에서 그래프 생성, 측정 데이터 스트림 수신, 센서 0점 조절 등을 밀리초(ms) 단위로 즉시 수행.

---

## 9. Codex 실행 플레이북 (Step-by-Step Playbook)

### Step 1: 환경 가드레일 및 브랜치 생성
```bash
git checkout -b feature/phase9-codebase-overhaul
```
- `tests/test_server_contract.py`에 도구 개수 12개 제한 테스트 추가.
- `automation_worker.py`의 `stderr=DEVNULL` 제거 및 에러 버퍼 파이프 도입.

### Step 2: 6대 복합 도구로 수렴 및 레거시 제거
- `src/capstone_mcp/tools/displays.py`, `instruments.py`, `graphs.py`의 레거시 단일 도구 제거.
- 복합 도구 6개(`manage_display`, `manage_graph`, `manage_instrument`, `manage_run`, `manage_file`, `manage_analysis`)로 등록 통폐합.
- `src/capstone_mcp/tutor/` 및 `tools/physics.py` 전량 삭제.

### Step 3: 정적 검사 및 CI 검증 (로컬)
```bash
# Windows 파일 락 방지
uv run --no-sync ruff check src tests
uv run --no-sync basedpyright src
uv run --no-sync pytest
```

### Step 4: Native QWebChannel 프로토타입 작성
- `src/capstone_mcp/native/qwebchannel_client.py`를 신설하여 Capstone 내부 `ViewModelHandler`와 WebSocket 직접 통신 프로토타입 검증.

---

**작성 완료**: 이 문서는 저장소의 [docs/specs/codex-handover-master-spec.md](file:///c:/Users/Jio/Documents/Codex/integrations/capstone-mcp/docs/specs/codex-handover-master-spec.md)에 위치하며, Codex가 작업을 즉시 개시할 수 있는 완전한 단일 진실 공급원(Single Source of Truth)입니다.
