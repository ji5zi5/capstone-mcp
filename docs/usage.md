# 사용 가이드

[README로 돌아가기](../README.md)

MCP 연결을 마쳤다면 AI 클라이언트의 채팅창에서 작업을 요청하면 됩니다. 이 문서는 작업별 진행 순서와 도구를 직접 호출할 때 필요한 인자를 설명합니다.

## 저장된 실험 파일 분석

파일 분석은 Capstone을 실행하거나 센서를 연결하지 않아도 사용할 수 있습니다. 파일 경로는 MCP 서버가 실행되는 Windows PC의 절대 경로로 지정하세요.

1. `capstone_inspect_file`로 센서·실험 설정과 계산식 등을 확인합니다.
   `hardware_interfaces`는 저장된 인터페이스별 센서이며,
   `unconnected_sensors`는 파일의 `UnconnectedSensor` 아래 저장된 센서입니다.
   두 목록은 저장 당시의 구성이며 현재 장치의 물리적 연결 상태를 증명하지 않습니다.
   전체 결과는 페이지 배치(`workspace`)와 `data_sources` 때문에 수십만 자가 될 수 있습니다.
   필요한 부분만 읽으려면 `sections`에 `["hardware_interfaces", "experiment_settings"]`처럼 지정하세요.
   요청하지 않은 구역은 `null`이며 `omitted_sections`에 이름이 남습니다.
2. `capstone_file_datasets`로 데이터셋의 이름, 인덱스, ID, 단위 ID, 샘플 수를 조회합니다.
   `run_name`과 `run_number`는 저장된 회차 이름과 번호입니다. 같은 회차의 데이터셋은
   측정 소스가 달라도 같은 `dataset_id`를 가지므로, x·y를 고를 때 이 값으로 짝을 맞춥니다.
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

같은 회차의 x·y를 좌표에 맞춰 짝지은 뒤 `capstone_linear_fit`에 전달합니다. 아래 숫자는 호출 형식을 보여 주는 예제입니다.

```json
{"samples":{"x":[0,1,2,3],"y":[1.1,2.8,5.2,6.9]}}
```

결과의 `diagnostics`에 잔차, 레버리지, Cook의 거리, 인접 잔차 상관이 있습니다. 회귀는 입력 표본 전체로 계산합니다. 표본별 진단 배열은 처음 256개까지 반환하고 `sample_count`·`truncated`로 범위를 표시합니다. 영향 표본의 인덱스도 최대 256개이며 전체 개수는 `influential_count`입니다. Cook의 거리 기준은 검토할 표본을 찾는 데 사용합니다.

`capstone_compare_runs`에는 같은 단위로 측정한 회차별 이름과 표본을, `capstone_plot`에는 좌표와 축 라벨을 전달합니다. 원본 파일, 데이터셋 인덱스, 회차와 축 단위를 분석 결과에 함께 기록하세요.

## 그래프 읽기와 피팅

`capstone_manage_graph`의 저장 파일 호출 예제입니다. 여러 그래프가 있으면 워크북 순서대로 0부터 번호를 매깁니다.

```json
{"request":{"action":"read","read":{"cap_file":"C:/Experiments/momentum.cap","graph_index":0}}}
```

저장 그래프에서 축의 소스·회차·단위와 네이티브 피팅 상태를 확인합니다. 미저장 그래프는 대상 창의 `read.handle`을 사용합니다. 이 경우 Capstone의 Copy Display가 필요합니다. 서버가 기존 클립보드 형식을 모두 백업하고 복사본 소유자를 확인한 뒤, 세대가 같을 때 복원합니다. 다른 앱의 더 최근 복사 내용은 보존합니다.

1. `capstone_attach`와 `capstone_windows`로 대상 창을 확인합니다. 새 그래프를 만들 때는 `capstone_manage_graph`의 `create`를 사용합니다.
2. `read`로 축·회차·단위와 `data_signature`를 확인합니다. `observe`에 실제 창 핸들과 `allow_foreground=true`를 넣어 원본 이미지와 일회용 `frame_id`를 받습니다. 축 메뉴는 `select_measurement`로 선택합니다.
3. 모델 피팅은 `analyze.fitting`에 원하는 전체 `models` 목록과 방금 읽은 `frame_id`, 화면에서 확인한 `menu_point`, 필요한 경우 `master_point`, `expected_data_signature`를 전달합니다. `fit` 동작은 그래프의 축 범위를 화면에 맞춥니다.
4. `analyze.outcome.fits_successful`과 실제 계수·오차 상태를 확인합니다. 실패하면 `capstone://status`의 `last_graph_failure`에서 요청과 실패 단계를 대조하고 다시 관찰합니다.

## 실행 중인 Capstone 조작

`capstone_snapshot`에서 창의 컨트롤과 `ref`를 찾습니다. 필요한 경우 `query`나 `control_types`로 범위를 줄입니다. `capstone_interact_ui`에 현재 참조나 화면에서 관측한 위치를 전달합니다. 입력 후에는 새 스냅샷이나 스크린샷으로 결과를 확인하세요. 열린 대화상자는 해당 대화상자의 핸들로 조작합니다.

| 하려는 일 | 도구와 확인할 내용 |
|---|---|
| 표, Digits, Scope, FFT, 페이지 | `capstone_manage_display`에 동작과 해당 페이로드를 지정합니다. 표는 열 이름을 확인하고 `read_table`로 페이지를 읽습니다. |
| 회차 이름·표시 상태 | `capstone_manage_run`으로 대상 회차를 확인합니다. 삭제 동작은 데이터 요약에서 확인되는 마지막 회차에만 적용됩니다. |
| 센서 선택·샘플링률 | `capstone_manage_instrument`의 `set_sampling_rate`에 실제 `sensor`와 지원되는 `target`을 넣고 반환된 선택과 속도를 확인합니다. |
| 발생기와 교정 | 발생기 설정 조회에는 `configure_signal_generator.read_only=true`를 사용합니다. 영점·교정은 관측한 센서와 기준값으로 확인합니다. |
| 기록 조건·수동 표본 | 타이머 조건과 `keep_sample` 요청을 지원합니다. 장치별 센서 역치 설정은 미지원입니다. 표본 보존 여부는 추가된 행 등 독립적인 관측으로 확인합니다. |
| 계산기 | `capstone_create_calculation`에 식과 선택적 단위를 전달합니다. 계산기에서 승인된 상태를 확인합니다. |

`capstone_manage_display`에서 현재 표의 첫 페이지를 읽는 예제입니다. 여러 표가 있으면 관측한 이름을 `read_table.table_name`에 지정합니다.

```json
{"request":{"action":"read_table","read_table":{"page":1,"page_size":20}}}
```

`capstone_save_experiment`는 새 `.cap` 경로에 저장하며 현재 문서 경로도 바뀝니다. `capstone_export_data`는 CSV와 요청한 행 미리보기를 반환합니다. 상위 폴더와 새 파일명을 준비하고 반환된 경로·크기·해시를 확인합니다. CSV는 표시 정밀도와 인덱스 정렬을 따릅니다. `capstone_open_experiment`로 다른 문서를 열기 전에 현재 실험의 저장 상태를 확인합니다.

## 실시간 조회

CDP를 사용하는 센서 조회에는 동일한 Capstone 프로세스의 루프백 디버깅 포트가 필요합니다. 작업 내용을 먼저 저장하고 Capstone을 종료한 후 PowerShell에서 실행합니다.

```powershell
$env:QTWEBENGINE_REMOTE_DEBUGGING = "127.0.0.1:9222"
Start-Process "C:/Program Files/PASCO scientific/Capstone/Capstone.exe"
Remove-Item Env:QTWEBENGINE_REMOTE_DEBUGGING
```

`capstone://measurements/live`에서 관측된 센서·측정 ID·단위·현재 값을 읽습니다. 누락값은 그대로 기록합니다. 응답 시각은 호스트 시계 기준입니다. `capstone://status`에는 연결 및 기록 상태, `capstone://hardware/inventory`에는 조회 가능한 장치 상태, `capstone://displays/active`에는 화면 정보가 있습니다. `capstone://runs/active`는 이 서버의 작업 목록을 표시합니다. 실험 회차별 수치는 저장된 데이터셋에서 확인하세요.

## 실험 분석과 보고서

`capstone_run_experiment_macro`의 `analyze`는 제공된 측정 배열을 분석합니다. 광전효과에 사용하는 호출 형식이며 아래 수치는 설명용입니다.

```json
{"experiment_id":"photoelectric_effect","action":"analyze","parameters":{"wavelengths_nm":[436,546,577],"stopping_voltages_v":[1.25,0.68,0.55]}}
```

RLC 공진, 강제진동, 단열기체, 슬릿 회절도 각 실험의 측정 배열을 입력합니다. `success`와 `phase_results`에서 실제로 완료된 단계를 확인합니다. 장비를 자동 구성하거나 센서 측정을 대신 수행하는 경로는 구현되지 않았습니다.

`capstone_generate_lab_report`는 저장 데이터 또는 명시적 입력에서 보고서를 만듭니다. 여러 회차나 축 후보가 있을 때는 파일에서 확인한 `run_id`와 `axes`를 사용합니다. 아래는 파일 선택과 출력 형식의 예제입니다.

```json
{"file_path_or_run":"C:/Experiments/momentum.cap","experiment_id":"generic","format":"both"}
```

실행 중인 서버의 전체 도구와 인자는 MCP의 `tools/list`에서 확인할 수 있습니다. `capstone_guide`에 `files`, `graphs`, `sensors`, `recovery` 등의 주제를 지정하면 해당 흐름을 읽을 수 있습니다.

## HTTP 연결

클라이언트가 Streamable HTTP 연결을 지원한다면 저장소 폴더에서 서버를 실행합니다.

```powershell
uv run --no-sync capstone-mcp-http
```

클라이언트의 MCP 서버 URL에 아래 주소를 등록하고 터미널을 실행 상태로 유지합니다. 서버는 로컬 루프백 주소에서만 수신합니다.

```text
http://127.0.0.1:8766/mcp
```

## 문제가 생겼을 때

| 증상 | 확인할 내용 |
| :--- | :--- |
| 클라이언트에 도구가 표시되지 않음 | `uv` 실행 가능 여부, `--directory`의 절대 경로, 클라이언트의 서버 로그를 확인합니다. |
| Capstone에 연결되지 않음 | 설치 경로와 실행 여부를 확인합니다. 여러 인스턴스가 있다면 대상 프로세스 ID를 지정합니다. Store 버전은 연결할 수 없습니다. |
| 입력이 "modal dialog"로 거부됨 | 오류에 나온 창(업데이트 안내, 대화상자 등)을 먼저 닫거나 처리합니다. |
| 조회 결과가 너무 커서 잘림 | `capstone_snapshot`은 `query`/`control_types`, `capstone_inspect_file`은 `sections`로 범위를 줄입니다. |
| 컨트롤 참조가 만료됨 | 새 스냅샷을 조회하고 반환된 `ref`로 다시 조작합니다. |
| 기록 버튼이 비활성화됨 | Capstone에서 센서 연결과 측정 소스 설정을 확인합니다. |
| 저장·내보내기가 중단됨 | 기존 대화상자, 출력 파일의 존재 여부, 상위 폴더를 확인합니다. |
| 네이티브 조작 시간이 초과됨 | 작업 프로세스가 종료되며 입력은 자동 재시도하지 않습니다. 앱의 측정·저장 상태를 확인한 뒤 `capstone_attach`로 다시 연결합니다. |
| 실시간 측정값을 조회할 수 없음 | 디버깅 포트를 지정해 앱을 다시 실행했는지, 해당 포트와 창이 같은 프로세스에 속하는지 확인합니다. |
| 지원하지 않는 저장 형식·측정값 오류 | 해당 데이터는 임의로 변환하지 않습니다. 설정 조회와 수치 추출은 별개이므로 설정만 읽히는 파일도 있습니다. |

화면 조작은 잠금이 해제된 로컬 데스크톱에서 사용하고, 여러 클라이언트가 같은 Capstone을 동시에 조작하지 않도록 하세요.
