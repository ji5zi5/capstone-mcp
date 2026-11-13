# ADR 0002: 브리지 통합 세션, 실물 스모크 분리, 런 도메인 재배치 및 프로세스 가드

- **상태 (Status)**: 승인됨 (Accepted)
- **일자 (Date)**: 2026-11-13
- **결정권자 (Deciders)**: 사용자, 에이전트

## 맥락 (Context)
1. `src/capstone_mcp/bridge.py`와 `automation_worker.py`가 완전히 분리되어 있어, 디버그 포트로 고속 조회가 가능한 센서 데이터까지 불필요하게 느린 UI 자동화를 거치고 있었음.
2. 524개 단위 테스트 중 상당수가 가짜 `Snapshot` 트리를 조작하는 Mock으로만 구성되어 있어 실제 런타임 연결성을 검증하지 못하고 있었음.
3. `rename_run`, `delete_run`, `set_run_visibility` 도구가 `runs/` 패키지가 아닌 `tools/displays.py`에 부적절하게 배치되어 있었음.
4. 백그라운드 프로세스가 소켓이나 바이너리 핸들을 점유하여 `uv run` 시 파일 락 오류(`os error 32`)가 지속 발생함.

## 결정 (Decision)
1. **통합 세션 어댑터 구축**:
   - 디버그 포트가 가용한 경우 센서 목록(`read_inventory`) 및 측정값(`read_measurement`)은 `bridge.py`를 최우선 고속 경로(Fast-path)로 사용함.
   - 레이아웃 구성, 그래프 조작 등 순수 화면 배치는 `AutomationWorker`를 통해 수행하는 통합 세션 계층을 도입함.
2. **실물 스모크 테스트 분리**:
   - 단위 테스트는 순수 데이터 변환, 수치 해석, 직렬화 로직 검증에 집중함.
   - 실제 로컬 `Capstone.exe` 설치 환경에서만 구동되는 전용 E2E 스모크 테스트(`tests/test_live_smoke.py`)를 신설하고, CI 환경에서는 `@pytest.mark.skipif(not HAS_CAPSTONE)` 가드로 안전하게 격리함.
3. **실험 런(Run) 관리 도메인 일원화**:
   - `tools/displays.py`에서 런 관리 도구들을 제거하고, `runs/` 패키지 기반의 `capstone_manage_run` 단일 복합 도구로 이관함.
4. **프로세스 수명주기 클린업 가드 보강**:
   - `atexit` 및 시그널 핸들러를 보강하여 서버 종료 시 자식 프로세스와 모든 소켓/JobObject 핸들을 즉시 강제 회수(Force Terminate)함으로써 `os error 32` 파일 락을 원천 차단함.
