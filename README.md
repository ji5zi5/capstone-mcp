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
| **실험 파일 분석** | 센서·실험 설정 조회, 데이터셋 추출, 산점도·선형 피팅·회차별 비교 |
| **Capstone 화면 조작** | 창과 컨트롤 조회, 클릭·입력, 드래그·스크롤, 스크린샷 |
| **저장·내보내기** | 새 `.cap` 파일로 저장, 저장 전 데이터를 CSV로 내보내기 |
| **센서 설정·측정 제어** | 센서 이름으로 선택, 목표 샘플링 속도 설정, 시작·정지·반복 측정 |

> 파일 분석, 화면 조작, 센서 설정, 저장·내보내기는 앱에서 확인했습니다. 실물 센서를 연결한 측정과 반복 측정은 아직 검증하지 않았습니다.

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
        "run", "capstone-mcp"
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

**데이터 분석**

> 지금 열린 Capstone 실험에 그래프를 추가하고, 같은 회차의 힘과 가속도를 축으로 지정해 선형 피팅을 적용해 줘.

**저장 전 데이터 추출**

> 현재 실험 데이터를 `C:/Experiments/current.csv`로 내보내고 처음 20행을 보여 줘.

**센서 설정**

> 현재 실험의 센서 목록을 확인하고, 내가 지정한 센서의 샘플링 속도를 100 Hz로 설정해 줘.

**반복 측정**

> 5초씩 3회 측정하고, 회차 사이에는 2초 쉬어 줘. 결과는 새 폴더 `C:/Experiments/session-01`에 회차별로 저장해 줘.

반복 측정에는 연결된 센서·측정 소스와 [추가 실행 설정](docs/usage.md#실시간-조회와-반복-측정)이 필요합니다. 센서 이름, 지원 속도, 데이터의 회차와 단위는 실제 실험에 맞게 선택하세요.

## 알아두기

- 화면 조작 시 Capstone 창이 앞으로 나올 수 있습니다. 잠금이 해제된 데스크톱에서 사용하세요.
- 저장·내보내기는 기존 파일을 덮어쓰지 않습니다. CSV는 화면 표시 정밀도를 따르므로 저장된 수치가 필요하면 `.cap` 파일에서 추출하세요.
- 그래프 생성·축 선택·선형 피팅은 Capstone 페이지에 직접 반영합니다. 별도 PNG와 저장 파일 분석 도구도 제공합니다.
- 내부 인터페이스와 화면 컨트롤을 이용하므로 Capstone 버전·화면 구성에 따라 일부 기능이 동작하지 않을 수 있습니다.

도구별 호출 방법, 반복 측정 설정, 오류 해결은 **[상세 사용 가이드](docs/usage.md)**에서 확인할 수 있습니다.
