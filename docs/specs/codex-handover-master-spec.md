# 📘 Codex 현실 기반 코드베이스 실사 및 단계적 개선 명세서 (Reality-Check & Remediation Spec)

**Document Version**: 2.1.0 (Rigorous Engineering & Boundary Verification)  
**Target Repository**: `capstone-mcp` (`main` branch)  
**Target Engineer/Agent**: OpenAI Codex & Maintainers  
**Date**: 2026-11-13  
**Status**: 증거(Evidence)와 가설(Hypothesis)의 엄격한 구분, IPC 파이프라인 전구간 엔드투엔드 검증 설계  

---

## 1. 개요 및 엔지니어링 원칙 (Core Principles)

이 문서는 "모든 것을 갈아엎자"는 성급한 가설이나 "코드 존재 = 실제 동작"이라는 성급한 일반화를 배제합니다.
**실제로 검증된 사실(Fact)**, **코드상 존재하는 구현(Existing Code)**, **실물 런타임 검증이 필요한 미확인 영역(Unverified)**, 그리고 **구체적인 기술적 에지 케이스(Edge Cases)**를 명확히 분리하여 기록합니다.

---

## 2. 코드베이스 현황 4분면 분석 (The 4 Quadrants of Ground Truth)

| 구분 | 검증된 사실 (Confirmed Facts) | 미확인 가설 및 추가 검증 필요 (Unverified Hypotheses) |
|---|---|---|
| **결함 및 리스크** | 1. `automation_worker.py:63`에서 `stderr=DEVNULL`로 자식 프로세스 트레이스백이 영구 유실됨.<br>2. `server.py:891-940`에서 예외 문자열의 `lower()` 부분 일치로 에러 코드를 추정하는 구조가 존재함.<br>3. 단위 테스트 다수가 가상 `Snapshot` 트리에 의존하여 실제 Qt GUI 동작을 완전 보증하지 못함. | 1. 문자열 기반 에러 분류가 실제 어떤 구체적 시나리오에서 오분류를 유발하는지 재현 테스트 필요.<br>2. 66개 개별 도구를 복합 도구로 통합할 때, 거대해진 내부 스키마가 실제로 LLM 컨텍스트 및 호출 오류율에 미치는 실측치 검증 필요.<br>3. 단위 테스트의 260개 Mock 중 순수 비즈니스 로직 격리용 Mock과 가짜 UI 자가당착 Mock의 파일별 분리 필요. |
| **자산 및 기능** | 1. `src/capstone_mcp/bridge.py` 파일에 CDP WebSocket(`Runtime.evaluate`)을 통해 센서 및 측정값을 요청하는 코드가 구현되어 있음.<br>2. `tools/physics.py`는 단순 퀴즈가 아니라 플롯 렌더링, OLS 선형 회귀, 계산식 등록, 실험 보고서 생성, 매크로 등 핵심 기능을 포함함. | 1. `bridge.py` 코드가 실제 실행 중인 Capstone 프로세스(`index.html`)와 연결되어 성공적으로 데이터를 가져오는지 실물 검증 필요.<br>2. Capstone의 `SenseAndControl` 웹뷰 및 `QWebChannel`이 그래프 생성, 스코프 트리거, 레이아웃 변경 등 전체 GUI 작업을 대체할 수 있는지는 **미확인 상태**임. |

---

## 3. 기존 구현 실사: `src/capstone_mcp/bridge.py`

새로운 통신 클라이언트를 작성하기 전에, 이미 작성된 `bridge.py`의 구조와 범위를 실물 환경에서 먼저 검증해야 합니다.

### 3.1 구현되어 있는 영역 (코드상 확인됨)
- **타깃 검색 (`discover_target`)**: `http://127.0.0.1:{port}/json/list` 엔드포인트에서 `/Capstone/Resources/www/index.html` 타깃을 자동 식별.
- **CDP WebSocket 통신 (`evaluate`)**: Chrome DevTools Protocol의 `Runtime.evaluate`를 통해 내부 자바스크립트 실행 및 결과 반환.
- **센서/측정값 조회 (`read_inventory`, `read_measurement`)**:
  - `window.app.mSenseAndControlView.mServices.RequestSensorsAndMeasurements()`
  - `window.app.mSenseAndControlView.mServices.RequestReadMeasurement(measurement_euid, unit_type)`

### 3.2 실증 검증이 필요한 한계 (GUI 대체 여부)
- `bridge.py`가 연결하는 대상은 Capstone 전체가 아니라 **`SenseAndControl` (코드 툴 웹뷰)** 패널입니다.
- 이 웹뷰 내부의 `mServices` 또는 `ViewModelHandler`가 워크북 레이아웃 변경, 그래프 생성, 축 설정, 오실로스코프 제어까지 지원하는지는 **직접 패킷을 관측하고 확인하기 전까지는 알 수 없습니다.**
- 따라서 **"GUI 자동화(`pywinauto`)를 즉시 전면 폐기하고 웹소켓으로 대체한다"는 주장은 미검증 가설**이며, UI 자동화는 실제 Capstone 런타임 제어의 중요한 축으로 유지/검증되어야 합니다.

---

## 4. `tools/physics.py` 및 `tutor/`의 기능 보존

`tools/physics.py`는 삭제 대상이 아니라, 순수 과학 계산 및 리포팅을 담당하는 핵심 도메인 모듈입니다.

### 4.1 보존해야 할 핵심 도구들
1. **`capstone_plot`**: 데이터 포인트로부터 인라인 PNG 산점도/선 그래프 렌더링 (`plotting.py`).
2. **`capstone_linear_fit`**: 최소자승법(OLS) 선형 회귀 분석 (`analysis.py`).
3. **`capstone_compare_runs`**: 복수 실험 런 간 통계 및 지표 비교.
4. **`capstone_create_calculation`**: Capstone 계산기에 수학 공식 및 물리 단위 등록.
5. **`capstone_generate_lab_report`**: `.cap` 아카이브나 런 데이터를 분석하여 이론값과의 오차 분석 및 논문/보고서 포맷(Markdown/HTML) 생성.
6. **`capstone_run_experiment_macro`**: 광전효과, RLC 공진, 단진동, 단열기체, 회절 실험의 다단계 매크로 실행.

### 4.2 분리 및 검토 대상 (선택적 제품 결정)
- 순수 퀴즈/과외 기능인 `capstone_tutor_get_lesson`, `capstone_tutor_guide_step` 및 `src/capstone_mcp/tutor/curriculum.py`의 분리 여부는 **아키텍처 결함이 아닌 제품 범위(Scope) 차원의 의사결정**입니다.
- 도구 수준에서 레거시 도구를 다룰 때 주의점: **현재 설치된 MCP SDK의 `ToolAnnotations`는 `deprecatedHint` 필드를 지원하지 않으므로(`title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`만 지원)** Pydantic 유효성 에러를 피하려면 설명 문서(docstring)를 통한 안내를 사용해야 합니다.

---

## 5. 확인된 실제 결함에 대한 엔드투엔드 수술 계획

추측에 기반한 전면 교체가 아닌, **실제로 드러난 결함 2가지**에 집중하여 안전하게 수정합니다.

### 5.1 과제 1: 자식 프로세스 `stderr` 수집 파이프라인 (에지 케이스 완비)
- **파일**: [src/capstone_mcp/automation_worker.py](file:///c:/Users/Jio/Documents/Codex/integrations/capstone-mcp/src/capstone_mcp/automation_worker.py#L63)
- **현상**: `stderr=subprocess.DEVNULL`로 인해 `native_main.py` 크래시 시 진단 정보 유실.
- **수술 요구사항**:
  1. `stderr=subprocess.PIPE`로 생성.
  2. **한 줄 무한 길이 방지**: 라인 단위 읽기 시 `readline(MAX_LINE_BYTES)` 또는 청크 단위 제한을 두어 메모리 고갈 방지.
  3. **프로세스 종료 직전 잔여 로그 회수**: 서브프로세스가 크래시/종료될 때 버퍼에 남은 마지막 출력(EOF 직전)까지 누락 없이 회수.
  4. **세션 재연결 시 로그 격리**: 작업자가 `reset()`되거나 재시작될 때 이전 세션의 잔류 로그가 섞이지 않도록 버퍼를 명시적으로 초기화.

### 5.2 과제 2: 전구간 엔드투엔드 구조화된 예외 전달 (IPC 파이프라인 관통)
- **현상**: 단순히 부모의 `server.py:format_tool_error`만 수정해서는 해결되지 않음.  
  자식 프로세스(`native_main.py` / `native_loop.py`)에서 예외가 발생할 때, [automation_models.py:136](file:///c:/Users/Jio/Documents/Codex/integrations/capstone-mcp/src/capstone_mcp/automation_models.py#L136)의 `NativeReply` 모델이 `error: str | None` 필드로 단순 문자열화하여 전송하고 있음.
- **수술 요구사항**:
  1. `NativeReply`에 구조화된 에러 페이로드 필드(`error_payload: ToolErrorPayload | None`) 추가.
  2. 자식 프로세스(`native_loop.py`)의 `dispatch_operation`에서 예외 발생 시 에러 코드와 원인을 직렬화하여 반환.
  3. 부모 프로세스(`automation_worker.py`)에서 단순 문자열 예외가 아닌 구조화된 `CapstoneError`를 발생.
  4. 최종 FastMCP 라우터(`server.py`)의 `format_tool_error`가 문자열 파싱 대신 이 구조화된 정보를 그대로 MCP 클라이언트에 전달.
  5. **오분류 재현 테스트 작성**: 그래프 관련 문자열이 포함된 디스플레이 오류 등 실제 오분류가 발생하는 구체적 케이스를 테스트로 먼저 고정.

---

## 6. 현실적인 검증 로드맵 (Reality-Check Roadmap)

1. **실제 환경 스모크 테스트 가동**:
   - `C:\Program Files\PASCO Scientific\Capstone\Capstone.exe`가 설치된 로컬 환경에서, 실제 GUI 테스트를 직접 실행하여 **실제로 동작하는 기능과 Mock에서만 통과하던 기능의 경계를 명확히 식별**.
2. **`bridge.py`의 실제 기능 범위 실측**:
   - 디버그 포트 9222를 띄운 Capstone에서 `evaluate`를 호출해보고, 어디까지 제어가 가능한지(단순 센서 값 읽기 vs UI 제어 가능 여부)를 실증 데이터로 확인.
3. **오분류 재현 테스트 선행 작성**:
   - 문자열 휴리스틱으로 인해 엉뚱한 에러 코드가 나오는 테스트를 먼저 작성하여 실패(Red)를 확인한 후, IPC 전구간 예외 직렬화 수정(Green) 착수.
