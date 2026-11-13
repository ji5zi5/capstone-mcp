# 📘 Codex 현실 기반 코드베이스 실사 및 단계적 개선 명세서 (Reality-Check & Remediation Spec)

**Document Version**: 2.0.0 (Pragmatic Engineering Revision)  
**Target Repository**: `capstone-mcp` (`main` branch)  
**Target Engineer/Agent**: OpenAI Codex & Maintainers  
**Date**: 2026-11-13  
**Status**: 검증된 사실(Fact), 기존 구현(Existing), 미검증 가설(Hypothesis), 개선 과제(Action Item)의 명확한 분리  

---

## 1. 개요 및 교훈 (Overview & Ground Truth)

이 문서는 "모든 것을 갈아엎자"는 성급한 가설 대신, **현재 코드베이스에서 실제로 검증된 결함**, **이미 존재하는 네이티브 브리지 구현**, **보존해야 할 실질적 기능**, 그리고 **실제 런타임 검증이 필요한 미확인 가설**을 명확히 구분하여 기록합니다.

---

## 2. 코드베이스 현황 4분면 분석 (The 4 Quadrants of Ground Truth)

| 구분 | 검증된 사실 (Confirmed Facts) | 미확인 가설 및 추가 검증 필요 (Unverified Hypotheses) |
|---|---|---|
| **결함 및 리스크** | 1. `automation_worker.py:63`의 `stderr=DEVNULL`로 자식 프로세스 트레이스백 유실.<br>2. `server.py:891-940`의 부분 문자열(`lower`) 검색식 에러 분류가 오분류 유발.<br>3. 단위 테스트 다수가 가상 `Snapshot` 트리에 의존하여 실제 Qt GUI 동작을 완전 보증하지 못함. | 1. 66개 개별 도구를 6개 복합 도구로 압축했을 때 실제 LLM 토큰/오류율이 개선되는가?<br>(복합 도구의 거대 스키마가 오히려 더 큰 컨텍스트를 소모하거나 인자 오류를 유발할 가능성).<br>2. 단위 테스트의 Mock이 실제 논리 검증 역할을 하는지, 단순 자가당착인지 파일별 실효성 미분석. |
| **자산 및 기능** | 1. `src/capstone_mcp/bridge.py`가 이미 존재하며, Qt 디버그 포트(CDP WebSocket)를 통해 센서 및 측정값을 실시간 조회하고 있음.<br>2. `tools/physics.py`는 단순 퀴즈가 아니라 플롯 렌더링, OLS 선형 회귀, 계산식 등록, 실험 보고서 생성, 매크로 등 핵심 기능을 수행함. | 1. Capstone의 `SenseAndControl` 웹뷰 및 `QWebChannel`이 그래프 생성, 스코프 트리거, 레이아웃 변경 등 전체 GUI 작업을 대체할 수 있는가?<br>(*현재까지 확인된 사실*: 센서/측정값 조회 외 GUI 대체 가능성은 미확인). |

---

## 3. 기존 구현의 재발견: `src/capstone_mcp/bridge.py`

새로운 통신 클라이언트를 무작정 작성하기 전에, 이미 안정적으로 구현된 `bridge.py`의 구조와 범위를 먼저 점검해야 합니다.

### 3.1 이미 구현되어 동작 중인 영역
- **타깃 검색 (`discover_target`)**: `http://127.0.0.1:{port}/json/list` 엔드포인트에서 `/Capstone/Resources/www/index.html` 타깃을 자동 식별.
- **CDP WebSocket 통신 (`evaluate`)**: Chrome DevTools Protocol의 `Runtime.evaluate`를 통해 내부 자바스크립트 실행 및 결과 반환.
- **센서/측정값 조회 (`read_inventory`, `read_measurement`)**:
  - `window.app.mSenseAndControlView.mServices.RequestSensorsAndMeasurements()`
  - `window.app.mSenseAndControlView.mServices.RequestReadMeasurement(measurement_euid, unit_type)`

### 3.2 실증 검증이 필요한 한계 (GUI 대체 여부)
- `bridge.py`가 연결하는 대상은 Capstone 전체가 아니라 **`SenseAndControl` (코드 툴 웹뷰)** 패널입니다.
- 이 웹뷰 내부의 `mServices` 또는 `ViewModelHandler`가 워크북 레이아웃 변경, 그래프 생성, 축 설정, 오실로스코프 제어까지 지원하는지는 **직접 패킷을 관측하고 확인하기 전까지는 알 수 없습니다.**
- 따라서 **"GUI 자동화(`pywinauto`)를 즉시 전면 폐기하고 웹소켓으로 대체한다"는 주장은 위험한 비약**이며, UI 자동화는 실제 Capstone 런타임 제어의 중요한 축으로 유지/검증되어야 합니다.

---

## 4. `tools/physics.py` 및 `tutor/`의 올바른 기능 보존

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
- 코드베이스를 깨뜨리지 않는 선에서 필요 시 튜터 라우터를 선택적으로 분리하거나 보존할 수 있습니다.

---

## 5. 확인된 실제 결함에 대한 즉각적인 수술 계획

추측에 기반한 전면 교체가 아닌, **실제로 드러난 결함 2가지**에 집중하여 안전하게 수정합니다.

### 5.1 과제 1: 자식 프로세스 `stderr` 수집 파이프라인 구축
- **파일**: [src/capstone_mcp/automation_worker.py](file:///c:/Users/Jio/Documents/Codex/integrations/capstone-mcp/src/capstone_mcp/automation_worker.py#L63)
- **현상**: `stderr=subprocess.DEVNULL`로 인해 `native_main.py` 크래시 시 진단 정보 유실.
- **수술**:
  1. `stderr=subprocess.PIPE`로 열기.
  2. 백그라운드 데몬 스레드에서 `stderr` 라인을 비동기적으로 읽어 `collections.deque(maxlen=200)`에 안전하게 적재.
  3. `process.poll() is not None` 또는 타임아웃 발생 시, 적재된 트레이스백을 추출하여 에러 메시지에 첨부.

### 5.2 과제 2: `server.py`의 정규화된 예외 처리
- **파일**: [src/capstone_mcp/server.py](file:///c:/Users/Jio/Documents/Codex/integrations/capstone-mcp/src/capstone_mcp/server.py#L891-L940)
- **현상**: 예외 문자열의 `lower()` 부분 일치(`"table" in lower`)로 인해 잘못된 에러 코드로 변환됨.
- **수술**:
  1. 커스텀 예외 클래스(`SessionNotAttachedError`, `ControlNotFoundError` 등)에 `error_code`와 `remediation` 속성을 부여.
  2. `format_tool_error`에서 문자열 휴리스틱 대신 예외 인스턴스의 속성을 최우선으로 참조하도록 리팩터링.

---

## 6. 현실적인 검증 로드맵 (Reality-Check Roadmap)

1. **실물 스모크 테스트 가동**:
   - `C:\Program Files\PASCO Scientific\Capstone\Capstone.exe`가 설치된 로컬 환경에서, `tests/test_protocol.py` 등 라이브 GUI 테스트를 직접 실행하여 **실제로 동작하는 기능과 Mock에서만 통과하던 기능의 경계를 명확히 식별**.
2. **`bridge.py`의 실제 기능 범위 조사**:
   - 디버그 포트 9222를 띄운 Capstone에서 `evaluate`를 호출해보고, 어디까지 제어가 가능한지(단순 센서 값 읽기 vs UI 제어 가능 여부)를 실증 데이터로 확인.
3. **도구 표면의 신중한 정돈**:
   - 도구를 맹목적으로 삭제하기보다, 이미 도입된 복합 도구(`capstone_manage_display`, `capstone_manage_graph`, `capstone_manage_instrument`)의 안정성을 높이고, 레거시 도구는 `deprecatedHint=True`를 활용하여 점진적으로 이관.
