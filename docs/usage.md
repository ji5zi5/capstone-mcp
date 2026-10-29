# 사용 가이드

[README로 돌아가기](../README.md)

MCP 연결을 마쳤다면 AI 클라이언트의 채팅창에서 작업을 요청하면 됩니다. 이 문서는 작업별 진행 순서와 도구를 직접 호출할 때 필요한 인자를 설명합니다.

## 저장된 실험 파일 분석

파일 분석은 Capstone을 실행하거나 센서를 연결하지 않아도 사용할 수 있습니다. 파일 경로는 MCP 서버가 실행되는 Windows PC의 절대 경로로 지정하세요.

1. `capstone_inspect_file`로 센서·실험 설정과 계산식 등을 확인합니다.
   `hardware_interfaces`는 저장된 인터페이스별 센서이며,
   `unconnected_sensors`는 파일의 `UnconnectedSensor` 아래 저장된 센서입니다.
   두 목록은 저장 당시의 구성이며 현재 장치의 물리적 연결 상태를 증명하지 않습니다.
2. `capstone_file_datasets`로 데이터셋의 이름, 인덱스, ID, 단위 ID, 샘플 수를 조회합니다.
3. 분석할 데이터셋을 선택해 추출하거나 피팅·비교합니다.

### 수치 추출

`capstone_extract_dataset` 호출 인자 예시입니다. `dataset_index`는 앞서 조회한 목록의 인덱스로 바꿉니다.

```json
{
  "path": "C:/Experiments/momentum.cap",
  "dataset_index": 0,
  "offset": 0,
  "limit": 100
}
```

`offset`과 `limit`으로 나누어 읽을 수 있습니다. 수치는 소수 문자열로 반환되며, `independent_kind`가 `index`인 좌표는 초 단위 시간이 아니라 샘플 번호입니다.

### 선형 피팅과 회차 비교

목록에서 x축과 y축 데이터셋을 확인한 뒤 `capstone_fit_file`에 전달합니다. 아래 인덱스는 설명용이며, 실제 파일에서 같은 좌표에 대응하는 두 수치 데이터셋을 골라야 합니다.

```json
{
  "path": "C:/Experiments/momentum.cap",
  "request": {
    "x": {"index": 0},
    "y": {"index": 1}
  }
}
```

- 인덱스 대신 `{"dataset_id": "조회한 데이터셋 ID"}`로 선택할 수도 있습니다. 두 선택 방식을 함께 지정하지 않습니다.
- `capstone_compare_file`은 `request.datasets`에 선택 목록을 받아 평균, 표본 표준편차, 최솟값·최댓값 등을 비교합니다. 비교 대상의 단위 ID가 같아야 합니다.
- 파일 분석 결과에는 원본 경로, 데이터셋과 측정 소스의 ID, 단위 정보가 포함됩니다. 자동 단위 변환은 하지 않습니다.
- `capstone_plot`은 추출한 x·y 값으로 PNG 그래프를 만듭니다. 피팅과 그래프는 별도 분석 결과이며 Capstone 내부 그래프를 편집하지 않습니다.

## 실행 중인 Capstone 조작

앱을 실행하고 실험을 연 다음 아래 순서로 연결합니다.

1. `capstone_attach`로 연결합니다. 여러 인스턴스 중 하나를 선택할 때는 `process_id`를 지정합니다.
2. `capstone_windows`로 대상 창의 `handle`을 확인합니다.
3. `capstone_snapshot`으로 컨트롤 이름과 참조값 `ref`를 읽습니다.
4. `capstone_action` 등으로 조작한 뒤 다시 조회해 결과를 확인합니다.

앱이 실행되어 있지 않다면 `capstone_attach`의 `launch: true`로 실행할 수 있습니다.

물리적 입력은 기본적으로 허용되어 Capstone 창을 활성화합니다. `allow_foreground: false`는 해당 입력을 차단하는 옵션이며, 백그라운드 조작으로 전환하는 옵션은 아닙니다. `ref`는 새 스냅샷이나 조작 후 만료되므로 재사용하지 마세요.

### Capstone 안에서 그래프와 피팅 만들기

그래프 작업을 요청하면 AI가 Capstone의 실제 페이지를 조작합니다. 좌표는 사용자가 외워서 입력하는 값이 아니라 AI가 현재 스크린샷에서 확인하는 위치입니다.

1. 현재 페이지를 확인합니다. 기존 표시를 보존하려면 `Add Page` 버튼으로 분석용 페이지를 추가합니다.
2. `capstone_create_graph(handle)`로 실제 그래프를 삽입합니다.
3. `capstone_screenshot(handle)`으로 축 선택 위치를 확인한 뒤, 각 축에 `capstone_select_graph_measurement(handle, axis_point, menu_path)`를 호출합니다. `menu_path`는 `["Index"]`, `["Init. Red v (m/s)"]`처럼 화면에서 확인한 정확한 메뉴 이름의 목록입니다.
4. `capstone_read_graph(handle)`으로 선택한 그래프의 실제 축 입력·회차·피팅 상태를 읽습니다. `capstone_fit_models()`로 지원 모델 이름을 조회합니다.
5. `capstone_set_graph_fits(handle, request)`에 `models` 목록과 `menu_point`(피팅 드롭다운 화살표), `master_point`(피팅 아이콘) 위치를 전달합니다. `["linear", "quadratic"]`는 두 모델만 남기는 요청이고, `[]`는 모두 제거하는 요청입니다. 이미 원하는 상태이면 모델을 다시 클릭하지 않습니다.
6. `fits_successful`과 `after.series[].fits[]`를 확인합니다. 모델 선택 성공과 수치 계산 성공은 다릅니다. 각 결과에는 Capstone의 `error_status`, 계수·불확도, 유효한 r·MSE·RMSE 등이 들어 있습니다. 실패한 피팅이나 유효하지 않은 통계값은 사용할 수 있는 숫자로 반환하지 않습니다.
7. 새 스크린샷에서 그래프와 주석을 확인합니다. 저장이 필요하면 `capstone_save_experiment`로 새 경로에 저장합니다.

축과 피팅 위치는 현재 클라이언트 영역 스크린샷의 원본 픽셀 좌표입니다. 창이나 그래프를 이동·크기 변경한 뒤에는 다시 확인해야 합니다. 그래프 내부 컨트롤은 UIA 트리에 나타나지 않으므로 고정 좌표를 재사용하지 않습니다.

비례·선형·가중 선형·2차·3차·다항식·멱함수·역함수·지수·로그·사인·감쇠 사인·가우시안 계열 등 **23개 내장 모델**을 선택할 수 있습니다. 사용자 정의 식 편집은 포함하지 않습니다. 전체 24행이 보이는 네이티브 메뉴를 기준으로 하므로 메뉴가 잘리지 않게 창을 충분히 크게 사용하세요. 특정 데이터에서 모든 모델이 수렴하는 것은 아니며, 네이티브 오류 상태를 그대로 확인해야 합니다.

`capstone_analyze_graph(handle, request)`는 이미 생성·선택한 그래프의 축 선택과 피팅·결과 읽기를 한 호출로 연결합니다. `request.x`와 `request.y`는 각각 `point`, `menu_path`를 가지며, 바꾸지 않을 축은 생략합니다. `request.fitting`에는 위 피팅 요청을 넣습니다. 그래프 생성 후 달라진 배치를 먼저 확인해야 하므로 이전 페이지 좌표로 바로 분석하지 않습니다.

그래프 상태는 저장 파일이나 외부 회귀 계산이 아니라 **Capstone의 Copy Display XML**에서 읽습니다. 이 과정에서 Windows 클립보드는 선택한 그래프로 바뀌지만 실험 파일은 저장되지 않습니다. `after.series[].inputs[]`는 각 렌더러의 소스·회차·단위 ID를 보존하며, 계수의 소수 문자열을 임의로 반올림하지 않습니다. 메뉴 동작 후 읽은 상태가 요청과 다르면 중단하고 불확실한 입력을 자동 재전송하지 않습니다.

`capstone_plot`과 파일 피팅은 별도 결과를 만드는 보조 도구입니다. Capstone 페이지에 결과를 반영해 달라는 요청을 이 도구만으로 완료 처리하지 않습니다.

### 센서와 샘플링 속도

측정이 정지된 상태에서 센서의 정확한 표시 이름을 확인합니다. `capstone_configure_sensor`의 `request`에 `sensor`와 `target`을 전달하면 센서 선택과 속도 설정을 함께 수행합니다.

예를 들어 대상 센서의 표시 이름을 `sensor`에, `"100 Hz"`를 `target`에 지정합니다. 목표값의 단위는 현재 표시 단위와 같아야 합니다. 지원되지 않는 속도를 요청하면 임의의 값으로 반올림하지 않고 선택한 센서의 이전 속도로 되돌립니다.

센서만 바꾸려면 `capstone_select_sensor`, 현재 속도에서 한 단계만 이동하려면 `capstone_step_sampling_rate`를 사용합니다.

### 저장과 CSV 내보내기

두 도구 모두 대상 창의 `handle`과 새 파일의 `path`를 받습니다. 저장할 상위 폴더를 미리 만들고, 열려 있는 대화상자는 닫아 두세요.

| 목적 | 도구 | 동작 |
| :--- | :--- | :--- |
| 실험 파일 보관 | `capstone_save_experiment` | 새 `.cap` 파일로 저장합니다. 현재 실험의 파일 경로도 바뀝니다. |
| 저장 전 데이터 읽기 | `capstone_export_data` | `.cap`을 저장하지 않고 전체 데이터를 CSV로 내보냅니다. |
| CSV의 다음 부분 읽기 | `capstone_csv_page` | 기존 CSV를 `offset`·`limit`으로 나누어 읽습니다. |

기존 파일은 덮어쓰지 않습니다. 저장·내보내기 결과에는 파일 경로, 크기, SHA-256 해시가 포함됩니다.

CSV 내보내기는 모든 데이터를 선택하고 **인덱스 기준**으로 정렬합니다. CSV 값은 Capstone의 표시 정밀도를 따르며, 헤더에서 측정 소스 ID나 시간 정렬을 추정하지 않습니다. 저장된 수치의 정밀도를 유지하려면 `.cap` 저장 후 데이터 추출 도구를 사용하세요.

## 실시간 조회와 반복 측정

실시간 설정·현재값 조회와 반복 측정에는 Capstone의 디버깅 포트가 필요합니다. 일반 화면 조작, 파일 분석, 저장·CSV 내보내기에는 이 추가 설정이 필요하지 않습니다.

기존 작업을 저장하고 Capstone을 닫은 뒤 PowerShell에서 실행합니다.

```powershell
$env:QTWEBENGINE_REMOTE_DEBUGGING = "127.0.0.1:9223"
Start-Process "C:/Program Files/PASCO scientific/Capstone/Capstone.exe"
Remove-Item Env:QTWEBENGINE_REMOTE_DEBUGGING
```

`capstone_live_configuration`으로 설정된 센서와 측정 소스를 조회하고, 반환된 측정 ID와 단위 ID를 `capstone_current_value`에 전달해 현재값을 읽습니다. 설정 목록에 센서가 있다는 사실만으로 실제 연결 상태를 판단하지는 않습니다.

### 반복 측정 준비

실물 센서를 연결한 측정은 아직 검증되지 않았습니다. 먼저 Capstone에서 대상 센서·측정 소스를 설정하고 기록 버튼이 활성화되어 있는지 확인하세요.

`capstone_repeat_acquisition`의 `plan`에 다음 항목을 지정합니다.

| 항목 | 설명 |
| :--- | :--- |
| `process_id`, `window_handle` | 연결한 Capstone 프로세스 ID와 대상 창 핸들 |
| `debug_port` | 위에서 지정한 디버깅 포트. 기본값 `9223` |
| `repetitions` | 측정 횟수, 1~100회 |
| `duration_seconds` | 회차별 측정 시간, 0초 초과~3600초 |
| `pause_seconds` | 회차 사이 대기 시간, 기본값 `0` |
| `capture.directory` | 자동 저장할 새 폴더 또는 빈 폴더. 생략하면 자동 저장하지 않음 |
| `capture.fit` | 선택 사항. 피팅할 x·y 측정 소스 ID |

프로세스 ID, 창 핸들, 디버깅 포트는 같은 Capstone 인스턴스를 가리켜야 합니다. 샘플링 속도는 반복 측정 전에 따로 설정합니다.

### 자동 저장·분석

`capture.directory`를 지정하면 측정 전 `baseline.cap`과 회차별 `run-001.cap`, `run-002.cap` 등의 파일이 생성됩니다. 각 파일은 해당 시점의 실험 전체를 저장한 스냅샷입니다.

자동 피팅을 사용하려면 `capture.fit`의 `x_source_euid`와 `y_source_euid`에 조회한 측정 소스 ID를 지정합니다. **측정 소스 ID와 데이터셋 ID는 서로 다릅니다.**

이전 스냅샷과 비교해 새로 추가된 샘플만 분석하고, 완료한 회차의 y값을 비교합니다. 새 샘플을 확실히 구분할 수 없으면 분석 오류를 반환합니다. 도중에 취소된 회차는 중단 여부와 저장 결과를 남기되 자동 피팅에서 제외합니다.

### 진행 상태와 취소

작업을 시작하면 `job_id`가 반환됩니다. `capstone_acquisition_job`으로 상태를 확인하고 `capstone_cancel_acquisition`으로 취소를 요청합니다.

취소 요청이 접수되었다고 측정이 즉시 끝난 것은 아닙니다. 상태가 `completed`, `cancelled`, `failed` 중 하나로 바뀌었는지 확인하세요. 실패한 경우에도 이미 저장된 파일과 회차 정보는 결과에 남을 수 있습니다. 반복 측정 중에는 다른 조작을 함께 보내지 마세요.

단일 시작·정지는 `capstone_set_recording`을 사용합니다. 응답의 `transition_pending`이 `true`라면 `capstone_recording_status`로 실제 상태를 다시 확인하세요.

## HTTP 연결

클라이언트가 Streamable HTTP 연결을 지원한다면 저장소 폴더에서 서버를 실행합니다.

```powershell
uv run capstone-mcp-http
```

클라이언트의 MCP 서버 URL에 아래 주소를 등록하고 터미널을 실행 상태로 유지합니다. 서버는 로컬 루프백 주소에서만 수신합니다.

```text
http://127.0.0.1:8766/mcp
```

## 문제가 생겼을 때

| 증상 | 확인할 내용 |
| :--- | :--- |
| 클라이언트에 도구가 표시되지 않음 | `uv` 실행 가능 여부, `--directory`의 절대 경로, 클라이언트의 서버 로그를 확인합니다. |
| Capstone에 연결되지 않음 | 설치 경로와 실행 여부를 확인합니다. 여러 인스턴스가 있다면 대상 프로세스 ID를 지정합니다. |
| 컨트롤 참조가 만료됨 | 새 스냅샷을 조회하고 반환된 `ref`로 다시 조작합니다. |
| 기록 버튼이 비활성화됨 | Capstone에서 센서 연결과 측정 소스 설정을 확인합니다. |
| 저장·내보내기가 중단됨 | 기존 대화상자, 출력 파일의 존재 여부, 상위 폴더를 확인합니다. |
| 네이티브 조작 시간이 초과됨 | 작업 프로세스가 종료되며 입력은 자동 재시도하지 않습니다. 앱의 측정·저장 상태를 확인한 뒤 `capstone_attach`로 다시 연결합니다. |
| 실시간 조회·반복 측정에 연결되지 않음 | 디버깅 포트를 지정해 앱을 다시 실행했는지, 해당 포트와 창이 같은 프로세스에 속하는지 확인합니다. |
| 지원하지 않는 저장 형식·측정값 오류 | 해당 데이터는 임의로 변환하지 않습니다. 설정 조회와 수치 추출은 별개이므로 설정만 읽히는 파일도 있습니다. |

화면 조작은 잠금이 해제된 로컬 데스크톱에서 사용하고, 여러 클라이언트가 같은 Capstone을 동시에 조작하지 않도록 하세요.
