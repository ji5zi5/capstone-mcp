# 감사 이슈 대조 원장 · 2026-11-27

기준은 `main`(`c57410e` → PR #150·#151·#152 병합 완료)이며, 각 조사 문서에서 원문 항목·코드·테스트·재현 조건과 남은 검증을 함께 볼 수 있다. #148 결정과 기존 트래커 동기화(#153~#156 분화 및 구 이슈 종결)까지 이 원장에 반영되어 있다. [실험 파일·CLI·패키징 PR #150](https://github.com/ji5zi5/capstone-mcp/pull/150) [런타임·실험 분석·공개 도구 안내 PR #151](https://github.com/ji5zi5/capstone-mcp/pull/151) [감사 대조·ADR 개정 PR #152](https://github.com/ji5zi5/capstone-mcp/pull/152)

## 무엇을 셌는가

1~3차 보고서에서 식별되는 ID 313개와 독립된 4차 보고서 제목의 ID 68개를 대조했다. 범위로 적은 ID는 펼치고, 두 보고서에 재수록된 항목은 한 번만 셌다. 고유 ID가 없는 보고서 19개의 원문 위치 111곳은 조사 문서에 별도로 연결했다. 한 위치가 여러 사례를 다루거나 다른 보고서와 겹쳐 이를 고유 결함 수로 환산할 수 없다. 기존 요약의 426건(358+68)에는 공식 개별 항목 대응표가 없다. [1~3차와 재수록 원문](../../EXHAUSTIVE_REPOSITORY_AUDIT_REPORT.md) [4차 원문](../../PHASE4_EXHAUSTIVE_EDGE_AUDIT_REPORT.md)

|원문 ID의 판정|수|집계 기준|
|---|---:|---|
|수정 완료|220|기준 코드 또는 제출한 구현 PR에서 해당 실패 경로를 막고 코드나 테스트로 확인한 항목|
|반증·오탐|71|실제 구현이나 데이터가 주장과 다르거나 현재 계약에서 의도한 동작인 항목|
|실기 검증 필요|74|실제 위젯·장비·희귀 파일 또는 기준 데이터가 있어야 진위를 가릴 수 있는 주장|
|확인한 Capstone API에 없음|8|조사한 버전의 래퍼·UI에 요구한 인터페이스가 없거나 제공된 증거로 연결할 수 없는 작업|
|미수정·추가 구현 필요|8|현재 제공하지 않는 수치 모델이나 입력 형식에 대해 구현과 수용 조건이 남은 항목|
|합계|381|각 ID는 아래 한 문서의 한 판정에만 포함|

## 조사 이슈와 구현 에픽

|조사|구현 에픽|ID 수|구현·네이티브 근거와 검토할 내용|
|---|---|---:|---|
|#139|#123|49|[워커·COM·동시성](reconcile_runtime_ipc.md) — 작업자 재시작, 요청 기한, 파일 감시 핸들 회수|
|#140|#124|25|[로컬 연결·파일 경로·아카이브](reconcile_security_archive.md) — 루프백 소유권, 경로 검사, ZIP·XML 경계|
|#141|#125|20|[그래프·클립보드](reconcile_graphs_clipboard.md) — 저장 파일 경로, 미저장 Copy Display의 복사 소유자와 세대 확인|
|#142|#126|58|[텔레메트리·계측기](reconcile_telemetry_instruments.md) — 단일 읽기, 시간 출처, 네이티브 설정 및 실기 판독|
|#143|#127|43|[FastMCP·계산기](reconcile_fastmcp_calculator.md) — stdio, 오류 응답, 수식 문법과 앱 승인|
|#144|#128|48|[UIA·런·디스플레이](reconcile_uia_runs_displays.md) — 최신 참조, 번역된 런 번호, 마지막 회차 삭제와 결과 관측|
|#145|#129|52|[물리 레시피·보고서·서비스 멤버](reconcile_recipes_numerics_reports.md) — 측정 출처, 수치식, 보고서 및 53개 멤버별 용도|
|#146|#130|86|[파일·언어·테스트](reconcile_files_locales_tests.md) — 저장 형식, 단위 변환기, CSV, 설치 라벨, 테스트 범위|

이전 백서의 A01·A02는 #141과 ADR 0005, B01~B03은 #139·#144, C01~C03은 #143·#146, D01·D02는 #142·#145와 ADR 0005에서 대조한다. 같은 주제에 붙은 백서별 기호를 위 총계에 더하지 않았다. [백서의 원문](../../EXHAUSTIVE_DEFECT_CATALOG.md) [개정 ADR 0005](../adr/0005-exhaustive-live-stabilization.md)

## 파일·앱·장비에서 얻은 근거

- 개인 실험 폴더의 하위 경로까지 포함한 `.cap` 36개를 읽었다. 데이터가 있는 파일과 설정 전용 파일은 각각 18개다. 데이터셋 332개에서 종속 표본 119,295개를 디코딩하여 데이터셋별 원문 개수와 독립 좌표 개수를 대조했고 저장 그래프 94개를 읽었다. 종속/독립 StorageType은 0/1 조합 264건, 7/4 조합 68건이며 모두 단일 세그먼트였다. 원본 파일 해시는 읽기 전후 일치했다. 공개 테스트에는 직접 작성한 재현용 XML을 사용했다. [파일 대조](reconcile_files_locales_tests.md) [실제 그래프 오류 수정](https://github.com/ji5zi5/capstone-mcp/pull/150)
- 설치된 Windows Capstone 2.5.0.10에서 물리 센서 없이 앱·워커 스모크 테스트 5개를 실행했다. 별도의 실제 stdio 검사에서는 테스트가 시작한 워크북의 PID·창을 선택해 컨트롤 트리, PNG 응답과 만료된 참조 거부를 확인했다. 저장소의 과거 덤프에는 생성자를 제외한 서비스 멤버 53개가 있다. 이번 설치의 래퍼에서도 53개 이름을 확인했다. 그중 51개 이름이 `Request`로 시작하며 측정 목록·개별 판독, 블록 편집, 참조 관리 등이 섞여 있다. [실기 테스트](../../tests/test_live_smoke.py) [53개 멤버 대조](reconcile_recipes_numerics_reports.md)
- 호스팅된 일회용 Windows에서 Unicode 텍스트와 등록 형식을 실제 클립보드에 적재하고 복원했다. 세대가 바뀐 경우 나중에 복사한 내용이 보존되는 것도 확인했다. 실제 미저장 Capstone 그래프의 Copy Display와 지연 렌더링 형식의 동시 사용은 별도 검증 대상이다. 사용자가 선택한 정책은 저장 파일을 직접 읽고, 미저장 그래프는 형식 보존·복사 소유권·세대를 검사해서 읽는 것이다. [Windows 실측](https://github.com/ji5zi5/capstone-mcp/actions/runs/45927775898) [ADR 0005](../adr/0005-exhaustive-live-stabilization.md)
- #83의 공개 사용 예시를 등록된 MCP 도구 22개와 리소스 6개에 대조했다. 저장 파일 읽기, 표본 회귀, 그래프, 표, 레시피와 보고서 예제의 입력 스키마를 확인했다. 네이티브 하드웨어 구성과 자동 측정이 구현된 것처럼 보였던 안내, 등록되지 않은 도구를 지시하던 서버 초기 안내·내장 프롬프트를 고쳤다. [사용 가이드](../usage.md) [서버와 회귀 검사](https://github.com/ji5zi5/capstone-mcp/pull/151)

## 우선순위와 남은 일

|우선순위|이 대조에서 남긴 작업과 수용 조건|
|---|---|
|P0|검사한 자료와 재현 환경에서 새로 확정되어 수정 대기 중인 P0는 `0건`이다. 기존 P0로 표시된 주장 중 파일 다중 세그먼트·Windows 경합은 [#155](https://github.com/ji5zi5/capstone-mcp/issues/155)로 이관했고, 실제 장비 중단은 하드웨어 미보유로 [#156](https://github.com/ji5zi5/capstone-mcp/issues/156)(`wontfix`) 종결했다. [기존 P0별 재현 조건](P0_REMAINING_2026-11-16.md)|
|P1|장비 출력·영점·기록 중단([#156](https://github.com/ji5zi5/capstone-mcp/issues/156))은 물리 하드웨어 미보유로 `wontfix` 종결했다(장비·재현 확보 시 재개). 코드 백로그로는 회절 잡음 극값 구분 모델(`DEFECT-DIFF02`)을 [#153](https://github.com/ji5zi5/capstone-mcp/issues/153)에 남겼으며, 계측 불확도·GUM 전파(`DIFF14`, `DIFF15`)는 #148 결정으로 현 안정화 범위 외(차기 확장)로 분리했다.|
|P2|CSV ISO 벽시계 열 시간대·원점·원문 보존 계약(`P2-L10N14`)은 [#154](https://github.com/ji5zi5/capstone-mcp/issues/154)에 남겼다. 회절 부분 픽셀 보간·고차 극소·결손 차수·간격 분산(`DIFF03`, `DIFF12`, `DIFF13`, `DIFF16`)은 #148 결정으로 차기 확장(`Out of scope`)으로 분리했다.|
|P3·확장|무명 보고서의 추가 레시피, 가중 피팅, 단열기체 온도·열량·자동 사이클 경계는 #148 결정으로 현 안정화 범위 외(차기 확장)로 분리했다. [수치 분석의 원문 및 근거](reconcile_recipes_numerics_reports.md)|

조사한 설치본에서 근거가 확인되지 않은 `100 kHz` 벌크 표본, 장비 시계 다채널 동기화, 범용 센서 설정 RPC, 임의 `.cap` 직접 합성은 [ADR 0005](../adr/0005-exhaustive-live-stabilization.md)에 따라 **미지원(범위 외)**으로 확정했다(공급자 명세나 실물 입출력 근거 확보 시 별도 재검토). #148 결정에 따라 **Phase 5(30인 스웜) 전체 조사는 공식 종결**하며, 아래 실기 검증이나 실사용 중 새 재현이 발생할 때만 해당 하위 모듈을 핀포인트로 조사한다.

### 잔여 백로그 및 에이전트 E2E 검증 이슈 (#153~#155)

- **코드 백로그 해결 완료 (`#153`, `#154`, Phase 2~3 확장 백로그 일괄 구현)**:
  - **#153 (`DEFECT-DIFF02`)**: [slit_diffraction.py](../../src/capstone_mcp/recipes/slit_diffraction.py)에 1D 위상 돌출도 필터링(`DEFAULT_MIN_PROMINENCE_RATIO = 0.005`, `min_prominence_ratio`, `min_prominence`), 선택적 삼각 이동평균(`smoothing_window`), 부분 픽셀 포물선 꼭짓점 보간(`DEFECT-DIFF03`), 다차수 회절 최소 선형 피팅(`DEFECT-DIFF12`), 이중슬릿 결손 차수 간격 복원 및 프린지 통계(`DEFECT-DIFF13`, `DIFF14`), GUM 표준·확장 불확도 전파(`DEFECT-DIFF15`, `DIFF16`) 구현 완료. ([test_recipes.py](../../tests/test_recipes.py), [test_phase2_recipes_and_reports.py](../../tests/test_phase2_recipes_and_reports.py))
  - **#154 (`P2-L10N14`)**: [csv_data.py](../../src/capstone_mcp/csv_data.py) 및 [csv_file.py](../../src/capstone_mcp/data_sources/adapters/csv_file.py)에 strict ISO 8601 타임스탬프 파싱(`CsvTimestampAxis`), 혼용 시간대/비ISO 행 fail-closed 차단, CSV 1행 기준 페이지네이션 원점 고정(`epoch_anchor_s`), 상대 경과 초 투영 및 `x_basis` 메타데이터 보존 구현 완료. ([test_csv_locales.py](../../tests/test_csv_locales.py))
  - **`보고서 #81` · `보고서 #102` 수치·레시피·리포트 보강**: [spectral.py](../../src/capstone_mcp/numerics/spectral.py) (`compute_power_spectrum` radix-2 FFT / exact DFT + Hann 창), [regression.py](../../src/capstone_mcp/numerics/regression.py) (`fit_weighted_linear_series`), [analysis.py](../../src/capstone_mcp/analysis.py) (`_sample_cooks_distance` 0-분산/leverage≈1 안전화, `r_squared` `[0, 1]` 클램핑), [polarization.py](../../src/capstone_mcp/recipes/polarization.py) (`PolarizationRecipe`, `fit_malus_law`), [adiabatic_gas.py](../../src/capstone_mcp/recipes/adiabatic_gas.py) (`weighted_log`, $\gamma < 1.0$ 아등온/비물리 차단, 다주기 행정 분할, 사이클 부호 분류, 온도/열역학 제1법칙 일관성 검사), [generator.py](../../src/capstone_mcp/reports/generator.py) (`polarization` 리포트·단열 안정성 검증), [desktop.py](../../src/capstone_mcp/desktop.py) (잠긴/비대화형 데스크톱 `AutomationError` 변환 가드) 및 HTTP 포트 충돌 종료 검증([test_http_lifecycle.py](../../tests/test_http_lifecycle.py)) 구현 완료. ([test_spectral_and_weighted_numerics.py](../../tests/test_spectral_and_weighted_numerics.py), [test_phase2_recipes_and_reports.py](../../tests/test_phase2_recipes_and_reports.py), [test_desktop_guards.py](../../tests/test_desktop_guards.py))
- **무센서 앱·`.cap` 파일 E2E 검증 (`#155` — 부분 실기 통과 + 대화형 데스크톱 실행 대기)**:
  - **에이전트 환경(`ThreadDesktop=exebox-...`) 내 실기 통과 범위**: `CAPSTONE_RUN_LIVE_TESTS=1 CAPSTONE_TEST_DISPOSABLE_CLIPBOARD=1` 실행으로 [test_live_smoke.py](../../tests/test_live_smoke.py) 6건, [test_native_clipboard.py](../../tests/test_native_clipboard.py) 1건, [test_live_e2e_app.py](../../tests/test_live_e2e_app.py) 비대화형 실기 2건(실제 `Capstone.exe 2.5.0.10` 기동·`Untitled.cap` UIA 메뉴/워크북 검증·PNG 스크린샷·모달/비활성 데스크톱 가드·스냅샷 10회 핸들/RSS 누수 검사·QuickStart 공식 데이터 `.cap` 코퍼스·stdio MCP 왕복) 통과 확인(`9 passed`).
  - **대화형 데스크톱(`WinSta0\Default`) 전용 UI 입력 범위**: `open_experiment`/`save_experiment`/`export_data`, `Copy Display`(`read_graph`), Table/Digits/Calculator 실제 UI 입력 3건(`test_live_e2e_interactive_*`)은 Windows 세션 경계(`exebox` 비입력 데스크톱 vs `WinSta0\Default`에서 OS가 `SetCursorPos`/`SetForegroundWindow` 차단)로 인해 에이전트 샌드박스에서는 `SKIPPED` 처리되었으며, 일반 콘솔에서 사용자 단회 실행 시 즉시 검증 가능(`#155`에 검증 결과 및 실행 명령 기록).
- **물리 850/550·센서 검증 (`wontfix`, `CLOSED`)** — [#156](https://github.com/ji5zi5/capstone-mcp/issues/156):
  - 물리 하드웨어 미보유로 현장 실기 검증을 수행할 수 없어 `wontfix`로 종결(장비 확보·현장 재현 시 재개).

### GitHub 이슈 동기화 결과

|이슈|최종 상태|반영 내용|
|---|---|---|
|#139~#147|`CLOSED`|조사 보고서 8건·개정 ADR 0005 채택 및 PR #152 병합으로 완료 종결|
|#148|`CLOSED`|백로그 2건 선별, 무센서/장비 분리, Phase 5 종결, 구 이슈 안 A 재편 합의|
|#83|`CLOSED`|PR #150·#151·#152에서 공개 도구 22개·리소스 6개·가이드 정렬 반영 후 완료 종결|
|#120|`CLOSED`|1~4차 감사·11/27 대조 완료, Phase 5 종결 및 잔여 항목 이관 후 종결|
|#123~#130|`CLOSED`|각 에픽에 11/27 판정 요약 및 `#153`~`#156` 이관 링크 기록 후 일괄 종결(`안 A`)|
|#156|`CLOSED` (`wontfix`)|물리 PASCO 850/550·센서 미보유로 현장 검증 불가 종결|
|#153·#154|`CLOSED`|회절 잡음/고차·불확도(#153), CSV ISO 8601(#154) 및 Phase 2~3 확장 백로그 일괄 구현·검증 후 종결|
|#155|`OPEN` (`ready-for-human`)|Capstone 2.5.0.10 실기 비대화형/`.cap`/클립보드/stdio 통과분 기록; 대화형 `WinSta0\Default` UI 3건 실행 대기|
|#138·#149|`CLOSED`|원장·트래커 동기화 완료 후 지도 및 정리 작업 최종 종결|
