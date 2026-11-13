# ADR 0003: CDP 기반 주력 텔레메트리 구축 및 UIA 보조 수단 격하

- **상태 (Status)**: 승인됨 (Accepted)
- **일자 (Date)**: 2026-11-13
- **결정권자 (Deciders)**: 사용자, 에이전트

## 맥락 (Context)
1. Capstone 2.13.4 리버싱 스파이크를 통해 내부 QtWebEngine이 53개의 C++ 네이티브 RPC 메서드(`window.app.mSenseAndControlView.mServices`)를 노출하고 있음을 규명함.
2. 기존 시스템은 단순 센서 값 조회나 설정까지도 느리고 깨지기 쉬운 UIA 화면 마우스 클릭에 의존하고 있어, 창 포커스 손실, 모달 팝업 가림, 화면 해상도/DPI 스케일링에 취약했음.
3. 도구 모듈(`tools/displays.py`, `tools/instruments.py`)에 35개의 레거시 개별 함수가 잔존하여 딥 모듈성을 저해하고 유지보수 표면을 비대하게 만들고 있음.
4. 데이터 소스 Seam(`data_sources/seam.py`)이 파일(`.cap`, `.csv`)만 문자열 경로로 지원하고 라이브 세션은 별도의 UIA 객체를 요구하여 다형성 Seam이 단절되어 있음.

## 결정 (Decision)
1. **CDP WebSocket 1순위 주력 인터페이스 확정**:
   - 센서 인벤토리 조회, 실시간 계측값 폴링, 역치 기반 정지 트리거, 데이터 주입 등 계측/데이터 관련 모든 동작은 CDP WebSocket(포트 9222)을 최우선 주력 경로(Primary Fast-Path, < 15ms)로 사용함.
   - UIA 데스크톱 마우스 자동화는 그래프 생성, 디스플레이 타일 배치, 파일 열기/저장 대화상자 등 화면 렌더링이 불가피한 영역에 한해 보조 수단(Auxiliary Fallback)으로 격하함.
2. **레거시 35개 패스스루 래퍼의 완전 삭제 (The Deletion Test)**:
   - `tools/displays.py` 및 `tools/instruments.py` 내부의 35개 레거시 개별 함수를 전량 삭제함.
   - 모든 클라이언트 및 단위 테스트는 오직 4대 복합 관리자(`manage_display`, `manage_graph`, `manage_instrument`, `manage_run`) 인터페이스만을 단일 테스트 표면으로 검증함.
3. **다형성 `live://` 데이터 소스 Seam 도입**:
   - `get_experiment_series(source, ...)`에 `live://` URI 체계를 도입하여, 호출자가 파일 경로와 동일하게 단일 문자열 URI(`live://measurements`, `live://table`)로 실시간 데이터를 질의할 수 있도록 인터페이스를 통합함.
