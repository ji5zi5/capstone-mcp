<h1 align="center">PASCO Capstone MCP</h1>

<p align="center">AI와 대화하며 Capstone 실험을 조작하고 데이터를 분석하세요.</p>

<p align="center"><strong>한국어</strong> · <a href="README.en.md">English</a></p>

<p align="center">
  <a href="#시작하기">시작하기</a> &nbsp;·&nbsp;
  <a href="#이렇게-요청하세요">사용 예시</a> &nbsp;·&nbsp;
  <a href="docs/usage.md">상세 사용 가이드</a>
</p>

---

PASCO Capstone MCP는 AI 클라이언트에서 **PASCO Capstone의 화면 조작, 실험 파일 추출, 수치 분석**을 사용할 수 있게 해 주는 비공식 MCP 서버입니다. MCP(Model Context Protocol)를 통해 AI가 로컬 PC의 Capstone 도구를 호출합니다.

저장된 `.cap` 파일을 분석하거나, 열려 있는 실험의 센서 설정과 측정 작업을 AI에 요청할 수 있습니다. 파일 분석만 할 때는 Capstone 앱을 실행하지 않아도 됩니다.

## 무엇을 할 수 있나요?

| 작업 | 제공 기능 |
| :--- | :--- |
| 실험 파일 분석 | 저장된 설정·데이터셋·회차·단위를 조회하고 표본을 추출합니다. 저장된 그래프의 축과 피팅 결과도 읽을 수 있습니다. |
| 수치 분석 | 같은 회차에서 짝지은 표본으로 산점도와 선형 회귀를 만들고 회차별 통계를 비교합니다. |
| Capstone 조작 | 창·컨트롤 조회, 스크린샷, 입력, 새 경로에 저장, CSV 내보내기를 지원합니다. |
| 그래프·디스플레이 | 그래프, 표, Digits, Scope, FFT와 페이지 배치를 다룹니다. 실제로 읽힌 값과 화면에 전달된 설정을 응답에서 확인합니다. |
| 센서·기록 | 센서 선택과 지원되는 샘플링 속도, 타이머 조건, 수동 표본을 요청합니다. 영점·교정과 850/550 발생기 출력은 실장비에서 확인해야 합니다. |
| 물리 실험·보고서 | 광전효과·RLC·강제진동·단열기체·슬릿 실험의 측정 배열을 분석합니다. 저장된 데이터로 Markdown·HTML 보고서를 생성합니다. |

## 시작하기

### 1. 설치

Windows, Git, [uv](https://docs.astral.sh/uv/), MCP 서버를 연결할 수 있는 AI 클라이언트가 필요합니다. Python은 3.12 이상을 사용합니다.

Capstone 앱을 조작하려면 PASCO Capstone이 아래 경로에 설치되어 있어야 합니다. 현재 앱 연결은 이 경로를 기준으로 동작합니다.

```text
C:/Program Files/PASCO scientific/Capstone/Capstone.exe
```

PowerShell에서 저장소를 내려받고 의존성을 설치합니다.

```powershell
git clone https://github.com/ji5zi5/capstone-mcp.git
cd capstone-mcp
uv sync --python 3.12
```

### 2. AI 클라이언트에 연결

클라이언트의 MCP 설정에 다음 항목을 추가합니다. `C:/Projects/capstone-mcp`는 저장소를 내려받은 **실제 폴더의 절대 경로**로 바꾸세요. 설정 파일의 위치와 등록 화면은 클라이언트마다 다릅니다.

```json
{
  "mcpServers": {
    "capstone": {
      "command": "uv",
      "args": [
        "--directory", "C:/Projects/capstone-mcp",
        "run", "--no-sync", "capstone-mcp"
      ]
    }
  }
}
```

설정을 적용하거나 클라이언트를 다시 시작한 뒤, `capstone` 서버와 `capstone_file_datasets` 같은 도구가 표시되는지 확인하세요. 이 방식은 클라이언트가 서버를 실행하므로 별도 터미널에서 서버를 켜 둘 필요가 없습니다.

HTTP 연결을 사용하는 경우에는 [사용 가이드](docs/usage.md#http-연결)를 참고하세요.

### 3. 첫 작업 요청

AI 클라이언트의 채팅창에서 작업을 요청합니다. 파일 경로는 **MCP 서버가 실행되는 Windows PC의 경로**를 사용하세요.

> `C:/Experiments/momentum.cap`에 어떤 데이터가 있는지 보여 줘. 각 데이터셋의 이름, 단위 정보, 샘플 수를 정리해 줘.

예시 경로를 실제 `.cap` 파일로 바꾸면 됩니다. 앱을 조작하려면 먼저 Capstone에서 실험을 열고, “실행 중인 Capstone에 연결해서 현재 창을 확인해 줘”라고 요청하세요.

## 이렇게 요청하세요

- **저장된 실험** — “이 파일의 회차와 단위를 확인하고, 시간과 속도가 함께 기록된 회차의 처음 20개 표본을 보여 줘.”
- **그래프** — “저장된 두 번째 그래프에서 축, 회차, 피팅 계수를 읽어 줘.” 열린 그래프에서 모델을 바꿀 때는 현재 창을 먼저 관찰하고 변경 후 네이티브 피팅 상태를 확인합니다.
- **저장 전 내보내기** — “열린 실험을 새 파일 `C:/Experiments/current.csv`로 내보내고 처음 20행을 보여 줘.”
- **광전효과** — “내가 기록한 파장(nm)과 저지전압(V) 배열로 플랑크 상수를 추정해 줘.”
- **센서** — “현재 연결된 힘 센서의 측정값과 단위를 확인해 줘.” 실시간 조회에는 같은 Capstone 프로세스에 연결된 로컬 디버깅 포트가 필요합니다. [설정 방법](docs/usage.md#실시간-조회)

## 알아두기

- 화면 조작 시 Capstone 창이 앞으로 나올 수 있습니다. 잠금이 해제된 데스크톱에서 사용하세요.
- 저장·내보내기는 기존 파일을 덮어쓰지 않습니다. CSV는 화면 표시 정밀도를 따르므로 저장된 수치가 필요하면 `.cap` 파일에서 추출하세요.
- 그래프 생성·축 선택·23종 내장 피팅을 Capstone 페이지에 직접 반영합니다. 같은 모델 설정을 다시 요청해도 피팅이 꺼지지 않습니다.
- 저장 그래프는 파일에서 읽습니다. 미저장 그래프는 Capstone의 Copy Display가 만든 클립보드 데이터의 소유자를 확인하고, 같은 세대일 때 지원 형식을 복원합니다.
- 내부 인터페이스와 화면 컨트롤을 이용하므로 Capstone 버전·화면 구성에 따라 일부 기능이 동작하지 않을 수 있습니다.

도구별 호출 방법, 실시간 조회 설정, 오류 해결은 **[상세 사용 가이드](docs/usage.md)**에서 확인할 수 있습니다.
