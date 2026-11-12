# Copyright 2026 Capstone MCP contributors.
"""Structured physics experiment curricula, apparatus checklists, and quiz models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class QuizQuestion:
    """Multiple choice or conceptual quiz question."""

    question: str
    options: list[str]
    correct_index: int
    explanation: str


@dataclass(frozen=True)
class ExperimentStep:
    """Specific procedural step in a physics experiment."""

    step_index: int
    title: str
    instructions: str
    safety_notes: str
    capstone_action: str
    validation_check: str


@dataclass(frozen=True)
class ExperimentCurriculum:
    """Complete pedagogical curriculum for a Capstone physics experiment."""

    experiment_id: str
    title: str
    domain: str
    equipment: list[str]
    theory_summary: str
    governing_equations: list[str]
    capstone_setup: dict[str, str]
    steps: list[ExperimentStep]
    quiz_questions: list[QuizQuestion]
    reference_file: str = ""


CANONICAL_EXPERIMENTS: dict[str, ExperimentCurriculum] = {
    "photoelectric_effect": ExperimentCurriculum(
        experiment_id="photoelectric_effect",
        title="광전 효과 (Photoelectric Effect)",
        domain="현대물리 (Modern Physics)",
        equipment=[
            "수은 분광 램프 (Mercury Light Source SE-6609)",
            "광전효과 측정기 본체 및 포토다이오드 (Photodiode Enclosure)",
            "DC 전류 증폭기 (DC Current Amplifier SE-9622)",
            "DC 전원 공급기 (DC Power Supply SE-9644, -4.5V ~ 0V)",
            "광학 트랙 (60cm Optical Track)",
            "850 Universal Interface & DIN 케이블",
            "파장 필터 세트 (365nm, 405nm, 436nm, 546nm, 577nm)",
        ],
        theory_summary=(
            "빛의 입자성(광자 모델)을 검증하고 플랑크 상수(h)와 금속의 일함수(phi)를 측정합니다. "
            "광자 에너지 E = hf 가 금속의 일함수 phi 보다 크면 광전자가 방출되며, "
            "저지전압 V를 인가하여 광전류가 0이 되는 지점을 측정합니다 (eV = hf - phi)."
        ),
        governing_equations=[
            "K_max = E - phi = hf - phi",
            "eV_0 = hf - phi",
            "V_0 = (h / e) * f - (phi / e)",
            "f_cutoff = phi / h",
        ],
        capstone_setup={
            "analog_ch_a": "DC Current Amplifier Interface (Signal Current)",
            "analog_ch_b": "DC Power Supply Interface (-4.5V ~ 0V Stopping Voltage)",
            "display": "Table (Wavelength, Frequency, Stopping Voltage, Current)",
            "sampling_mode": "Keep Sample (Manual Sampling on Preview)",
        },
        steps=[
            ExperimentStep(
                step_index=1,
                title="장비 설치 및 예열",
                instructions="트랙 위에 수은 램프와 포토다이오드를 35cm 간격으로 설치하고, 수은 램프를 10분 이상 충분히 예열합니다.",
                safety_notes="수은 램프에서 방출되는 자외선 불빛을 맨눈으로 직접 응시하지 마십시오.",
                capstone_action="Capstone에서 EX-5549A Photoelectric Effect 템플릿을 열거나 아날로그 채널 A/B를 설정합니다.",
                validation_check="수은 램프가 안정적으로 켜져 있고 채널 A/B 케이블이 인터페이스에 단단히 결합되어 있는지 확인합니다.",
            ),
            ExperimentStep(
                step_index=2,
                title="전류 증폭기 영점 교정 (Calibration)",
                instructions="DC 전류 증폭기의 CURRENT RANGES 스위치를 10^-13 A로 설정하고, SIGNAL 버튼을 눌러 Calibration 모드에서 0.000 A가 되도록 노브를 조절합니다.",
                safety_notes="실험 도중 전류 증폭기의 게인이나 영점 노브를 건드리지 마십시오.",
                capstone_action="SIGNAL 버튼을 다시 눌러 Measure 모드로 전환합니다.",
                validation_check="암실/빛 차단 상태에서 전류계 표시창이 0.000 A에 머무르는지 확인합니다.",
            ),
            ExperimentStep(
                step_index=3,
                title="파장별 저지전압 측정 및 Keep Sample",
                instructions="조리개를 8mm, 필터를 365nm(8.219 x 10^14 Hz)에 맞추고 Capstone 하단의 Preview를 클릭합니다. 전류가 정확히 0이 될 때까지 전원 공급기 전압 손잡이를 미세 조절한 후 Keep Sample을 누릅니다.",
                safety_notes="전압 노브를 급격하게 돌리지 말고 천천히 0A 지점을 찾습니다.",
                capstone_action="각 파장(365, 405, 436, 546, 577 nm)에 대해 저지전압을 표에 순차적으로 기록합니다.",
                validation_check="단파장(365nm)일수록 높은 저지전압(음의 전위차 크기 증가)이 나타나는지 확인합니다.",
            ),
            ExperimentStep(
                step_index=4,
                title="선형 회귀 및 플랑크 상수(h) 산출",
                instructions="Capstone 그래프에서 저지전압 vs 진동수(V vs f) 데이터를 선형 피팅(Linear Fit: y = mx + b)합니다.",
                safety_notes="데이터 이상치가 있는 경우 특정 회차의 샘플을 재측정합니다.",
                capstone_action="그래프 맞춤 도구상자에서 Linear Fit을 적용하고 기울기(m)와 y절편(b)을 확인합니다.",
                validation_check="기울기 m = h/e 이므로, h = m * 1.602 x 10^-19 J·s가 공인값(6.626 x 10^-34 J·s)과 오차 10% 이내인지 검증합니다.",
            ),
            ExperimentStep(
                step_index=5,
                title="빛의 세기별 저지전압 불변성 검증",
                instructions="필터를 436nm로 고정한 후, 조리개 직경을 2mm, 4mm, 8mm로 변경하며 저지전압을 측정합니다.",
                safety_notes="조리개 휠을 회전할 때 광학 트랙 정렬이 흐트러지지 않도록 주의합니다.",
                capstone_action="조리개 구경에 따라 광전류 크기는 변하지만 저지전압은 일정함을 확인합니다.",
                validation_check="빛의 세기가 증가해도 저지전압이 변하지 않는 입자성(광양자설)의 핵심 증거를 확인합니다.",
            ),
        ],
        quiz_questions=[
            QuizQuestion(
                question="광전 효과 실험에서 빛의 진동수를 증가시키면 방출되는 전자의 어떤 물리량이 증가합니까?",
                options=[
                    "최대 운동 에너지 (저지전압)",
                    "방출되는 광전자의 총 개수",
                    "금속의 고유 일함수 크기",
                    "전자의 기본 기본 전하량",
                ],
                correct_index=0,
                explanation="E = hf - phi 이므로 진동수가 증가하면 광전자의 최대 운동 에너지가 선형적으로 증가합니다.",
            ),
            QuizQuestion(
                question="저지전압(V) 대 진동수(f) 그래프에서 직선의 기울기가 나타내는 물리적 의미는 무엇입니까?",
                options=[
                    "h / e (플랑크 상수를 기본 전하량으로 나눈 값)",
                    "phi / e (금속의 일함수 전위)",
                    "e / h (기본 전하량과 플랑크 상수의 비)",
                    "c (진공에서의 빛의 속도)",
                ],
                correct_index=0,
                explanation="식 V = (h/e)f - (phi/e) 로부터 기울기는 h/e를 직접 나타냅니다.",
            ),
        ],
        reference_file="0001-photoelectric-effect.html",
    ),
    "rlc_resonance": ExperimentCurriculum(
        experiment_id="rlc_resonance",
        title="LRC 직렬 공진 회로 (RLC Circuit Resonance)",
        domain="전자기학 (Electromagnetism)",
        equipment=[
            "RLC 회로 보드 (CI-6512, R=10 Ohm, L=8.2 mH / 18.9 mH, C=100 uF / 10 uF)",
            "850 Universal Interface (신호발생기 Output #1)",
            "전압 센서 3개 (UI-5100, Analog Ch A, B, C)",
            "바나나 플러그 케이블 세트",
        ],
        theory_summary=(
            "교류 전압이 인가된 RLC 직렬 회로에서 주파수 변화에 따른 전류 및 임피던스 변화를 관찰합니다. "
            "유도 리액턴스(X_L = omega L)와 용량 리액턴스(X_C = 1 / (omega C))가 같아지는 공진 주파수 "
            "f_0 = 1 / (2 pi sqrt(LC)) 에서 회로의 임피던스는 최소값(R)이 되고 저항에 걸리는 전류가 최대가 됩니다."
        ),
        governing_equations=[
            "Z = sqrt(R^2 + (X_L - X_C)^2)",
            "X_L = 2 pi f L,  X_C = 1 / (2 pi f C)",
            "f_0 = 1 / (2 pi sqrt(L C))",
            "tan(phi) = (X_L - X_C) / R",
            "Q = (1 / R) * sqrt(L / C) = f_0 / Delta f",
        ],
        capstone_setup={
            "signal_generator": "Output 1: Sine Wave, 10 Hz ~ 5 kHz, Amplitude 1.0 V, Auto Mode",
            "analog_ch_a": "Voltage across Resistor (V_R)",
            "analog_ch_b": "Voltage across Inductor (V_L)",
            "analog_ch_c": "Voltage across Capacitor (V_C)",
            "display": "Scope Display & FFT Frequency Spectrum",
        },
        steps=[
            ExperimentStep(
                step_index=1,
                title="회로 결선 및 신호발생기 연결",
                instructions="10 Ohm 저항, 8.2 mH 코일, 100 uF 축전기를 직렬 결선하고 850 Signal Generator Output 1과 연결합니다.",
                safety_notes="전선 극성을 일치시키고 쇼트가 발생하지 않도록 주의합니다.",
                capstone_action="Signal Generator 창에서 Sine 파형, 주파수 10Hz, 진폭 1V, Auto 스위치를 설정합니다.",
                validation_check="오실로스코프 화면에서 안정된 1Vpp 사인파가 관측되는지 확인합니다.",
            ),
            ExperimentStep(
                step_index=2,
                title="주파수 스윕 및 공진 피크 관찰",
                instructions="신호발생기 주파수를 점진적으로 증가시키며 저항 양단 전압(V_R)의 진폭 변화를 모니터링합니다.",
                safety_notes="최대 출력 전압이 10V를 넘지 않도록 안전 범위를 유지합니다.",
                capstone_action="주파수별 V_R 전압 진폭을 기록하고 공진 주파수 근처에서 1Hz 단위로 미세 조절합니다.",
                validation_check="V_R 전압이 피크에 도달하고 입력 전압과의 위상차가 0이 되는 주파수를 확인합니다.",
            ),
            ExperimentStep(
                step_index=3,
                title="위상 관계 및 Q 인자 분석",
                instructions="공진 주파수보다 낮은 영역, 공진점, 높은 영역에서 V_R과 V_in 간의 시간차 Delta t를 측정하여 위상각을 계산합니다.",
                safety_notes="FFT 창과 오실로스코프 창의 트리거 레벨을 고정합니다.",
                capstone_action="FFT 디스플레이에서 대역폭 Delta f (전력 반치점 -3dB)를 측정하여 Q = f_0 / Delta f 를 산출합니다.",
                validation_check="이론적 공진주파수 1/(2 pi sqrt(LC))와 실험치의 오차율을 계산합니다.",
            ),
        ],
        quiz_questions=[
            QuizQuestion(
                question="RLC 직렬 회로가 공진(Resonance) 상태에 도달했을 때 회로의 임피던스(Z)는 어떤 상태가 됩니까?",
                options=[
                    "최소화되며 저항 R의 크기와 동일해진다",
                    "최대화되며 전류의 흐름이 완전히 차단된다",
                    "유도 리액턴스 X_L 만 남아 매우 커진다",
                    "용량 리액턴스 X_C 에 의해 무한대가 된다",
                ],
                correct_index=0,
                explanation="X_L = X_C 가 상쇄되므로 Z = sqrt(R^2 + 0) = R 로 임피던스가 최소가 됩니다.",
            ),
        ],
        reference_file="0002-rlc-resonance.html",
    ),
    "forced_harmonic_oscillation": ExperimentCurriculum(
        experiment_id="forced_harmonic_oscillation",
        title="강제 조화 진동 및 감쇠 (Driven Damped Oscillations)",
        domain="고전역학 (Classical Mechanics)",
        equipment=[
            "스마트 카트 (Smart Cart ME-1240, 내장 가속도/힘/위치 센서)",
            "기계적 진동 드라이버 (Mechanical Oscillator/Driver ME-8750)",
            "자기 감쇠 액세서리 (Magnetic Damping Accessory ME-6828)",
            "역학 트랙 (1.2m Metal Dynamics Track ME-9493)",
            "스프링 세트 (Dynamics Spring Set ME-8999)",
            "포토게이트 (ME-9498A)",
        ],
        theory_summary=(
            "용수철에 연결된 카트의 강제 진동 운동을 분석합니다. 구동 주파수(omega)가 고유 진동수(omega_0)에 "
            "접근할 때 나타나는 공진 현상과, 트랙에 작용하는 와전류 자기 감쇠(b)에 따른 진폭 감쇠 및 위상 지연을 규명합니다."
        ),
        governing_equations=[
            "m d^2x/dt^2 + b dx/dt + kx = F_0 cos(omega t)",
            "omega_0 = sqrt(k / m)",
            "x_0(omega) = (F_0 / m) / sqrt((omega^2 - omega_0^2)^2 + (b omega / m)^2)",
            "tan(phi) = (b omega / m) / (omega_0^2 - omega^2)",
        ],
        capstone_setup={
            "wireless_sensors": "Smart Cart Position (100 Hz), Force Sensor (25 Hz)",
            "digital_ch_1": "Photogate Pendulum Timer (Driver Period)",
            "recording_condition": "Automatic Stop Condition after 480 seconds",
            "display": "Position vs Time Graph, Amplitude vs Frequency Graph",
        },
        steps=[
            ExperimentStep(
                step_index=1,
                title="스마트 카트 및 드라이버 셋업",
                instructions="트랙 끝에 기계식 드라이버를 장착하고, 카트 양 끝에 스프링을 연결하여 평형을 맞춥니다.",
                safety_notes="스마트 카트 바퀴와 센서에 무리한 충격이 가지 않도록 주의합니다.",
                capstone_action="블루투스로 스마트 카트를 페어링하고 위치 100Hz, 힘 25Hz를 설정합니다.",
                validation_check="카트 수동 진동 시 자유 감쇠 진동 파형이 매끄럽게 기록되는지 확인합니다.",
            ),
            ExperimentStep(
                step_index=2,
                title="고유 진동수(omega_0) 측정",
                instructions="드라이버 전원을 끈 상태에서 카트를 당겼다 놓아 자유 진동 주기를 측정합니다.",
                safety_notes="진폭이 용수철 탄성 한계를 넘지 않도록 5cm 이내로 유지합니다.",
                capstone_action="위치 그래프에서 주기 T를 측정하여 omega_0 = 2 pi / T 를 계산합니다.",
                validation_check="용수철 상수 k와 카트 질량 m으로부터 이론 고유진동수 sqrt(k/m)와 비교합니다.",
            ),
            ExperimentStep(
                step_index=3,
                title="구동 주파수 스윕 및 공진 곡선 획득",
                instructions="드라이버 주파수를 0.5Hz부터 점진적으로 증가시키며 각 주파수에서의 정상 상태 진폭을 측정합니다.",
                safety_notes="공진 영역에서 진폭이 과도하게 커지면 즉시 드라이버 진폭 노브를 줄입니다.",
                capstone_action="자동 정지 조건을 480초로 설정하고 진폭 대 주파수 응답 곡선을 완성합니다.",
                validation_check="공진 주파수에서 진폭이 극대값을 형성하고 자기 감쇠 증가 시 피크가 낮아지고 넓어지는지 관찰합니다.",
            ),
        ],
        quiz_questions=[
            QuizQuestion(
                question="강제 진동 시스템에서 감쇠 계수(b)가 증가하면 공진 피크(Resonance Peak)의 형태는 어떻게 변화합니까?",
                options=[
                    "최대 진폭이 감소하고 공진 대역폭이 넓어진다",
                    "최대 진폭이 증가하고 공진 주파수가 높아진다",
                    "공진 주파수가 정확히 2배로 증가하여 좁아진다",
                    "진폭과 대역폭 모두 아무런 변화가 발생하지 않는다",
                ],
                correct_index=0,
                explanation="감쇠 계수 b가 커지면 분모의 감쇠항이 커져 최대 진폭은 낮아지고 대역폭은 넓어지는 Q-factor 저하가 일어납니다.",
            ),
        ],
        reference_file="0003-forced-oscillation.html",
    ),
    "adiabatic_gas": ExperimentCurriculum(
        experiment_id="adiabatic_gas",
        title="단열 기체 법칙 및 열기관 사이클 (Adiabatic Gas & Heat Engine)",
        domain="열역학 (Thermodynamics)",
        equipment=[
            "단열 기체 실험 장치 (Adiabatic Gas Law Apparatus TD-8565)",
            "열기관 사이클 장치 (Heat Engine Cycle Apparatus EX-5530B)",
            "압력 센서 (Absolute Pressure Sensor)",
            "부피/변위 센서 (Linear Position / Volume Sensor)",
            "온도 센서 (Fast-response Temperature Sensor)",
            "850 Universal Interface (1000 Hz Sampling)",
        ],
        theory_summary=(
            "기체의 급격한 압축 및 팽창 과정에서 열 출입이 차단된 단열 상태(Q = 0)의 상태 방정식 "
            "P V^gamma = const 를 검증합니다. 또한 열기관 4행정 닫힌 사이클의 P-V 선도를 작성하고 "
            "선도 내부 면적 적분(W = oint P dV)을 통해 기체가 수행한 역학적 일과 효율을 측정합니다."
        ),
        governing_equations=[
            "P * V^gamma = constant",
            "T * V^(gamma - 1) = constant",
            "W_cycle = oint P dV",
            "gamma = C_p / C_v  (공기의 경우 약 1.40)",
        ],
        capstone_setup={
            "analog_sensors": "Pressure (kPa, 1000 Hz), Volume (cm^3, 1000 Hz), Temperature (K)",
            "display": "P vs V Graph with Area Integral Tool",
            "recording_condition": "Fast Burst Mode (Trigger on rapid compression)",
        },
        steps=[
            ExperimentStep(
                step_index=1,
                title="단열 실린더 압축 레버 설정",
                instructions="실린더 피스톤 레버를 상단에 고정하고 압력, 부피, 온도 센서의 영점을 교정합니다.",
                safety_notes="피스톤을 강하게 누를 때 손가락이 끼이지 않도록 주의하십시오.",
                capstone_action="샘플링 속도를 1000 Hz로 올리고 압력 vs 부피 그래프를 생성합니다.",
                validation_check="상온 대기압(약 101.3 kPa) 및 초기 부피가 올바르게 표시되는지 확인합니다.",
            ),
            ExperimentStep(
                step_index=2,
                title="급격한 단열 압축 실행",
                instructions="기록을 시작하고 피스톤 레버를 순간적으로(0.1초 이내) 강하게 압축합니다.",
                safety_notes="실린더 파손 방지를 위해 정격 압축 행정 범위를 초과하지 마십시오.",
                capstone_action="압축 순간의 P, V 곡선을 확인하고 지수 회귀(Power Fit: y = A * x^B)를 실행합니다.",
                validation_check="B의 지수값이 -1.40 (단열지수 gamma)에 근접하는지 확인합니다.",
            ),
            ExperimentStep(
                step_index=3,
                title="열기관 순환 과정 면적 적분",
                instructions="열기관 사이클(온수조-냉수조)을 거치며 닫힌 폐곡선 P-V 선도를 형성합니다.",
                safety_notes="온수조 사용 시 화상에 주의하십시오.",
                capstone_action="Capstone 그래프 도구상자의 Area Integral 도구를 적용하여 사이클 순작업 W = oint P dV를 계산합니다.",
                validation_check="적분 일(W)과 질량 추를 들어올린 역학적 위치에너지 변화(Delta U = mgh)를 비교합니다.",
            ),
        ],
        quiz_questions=[
            QuizQuestion(
                question="이상기체가 이상적인 단열 압축(Adiabatic Compression)을 겪을 때 내부 온도와 압력은 어떻게 됩니까?",
                options=[
                    "외부에서 한 일에 의해 내부 에너지가 증가하여 온도와 압력이 모두 상승한다",
                    "단열 상태이므로 열량이 불변하여 온도와 압력 모두 일정하게 유지된다",
                    "부피가 감소하면서 압력은 증가하지만 온도는 급격히 하강한다",
                    "등온 과정과 동일하게 압력은 부피에 정확히 반비례하고 온도는 불변한다",
                ],
                correct_index=0,
                explanation="Q = 0 이므로 dU = dW_in > 0 이 되어 기체의 내부 에너지와 온도가 증가하고 압력도 급격히 상승합니다.",
            ),
        ],
        reference_file="0004-adiabatic-gas.html",
    ),
    "slit_diffraction": ExperimentCurriculum(
        experiment_id="slit_diffraction",
        title="빛의 간섭과 회절 (Light Interference & Diffraction)",
        domain="광학 (Optics)",
        equipment=[
            "광학 벤치 (Optics Bench OS-8441, 1.2m)",
            "반도체 다이오드 레이저 (Red Diode Laser, 650 nm)",
            "단일 슬릿 / 이중 슬릿 디스크 (Slit Accessory Wheel)",
            "고감도 광센서 (High Sensitivity Light Sensor CI-6504 / PS-2106A)",
            "회전 운동 센서 (Rotary Motion Sensor for Linear Translation)",
        ],
        theory_summary=(
            "빛의 파동성을 입증하는 대표적인 프라운호퍼 회절 및 영(Young)의 이중 슬릿 간섭 현상을 관찰합니다. "
            "슬릿 폭 a에 따른 회절 극소 조건(a sin(theta) = m lambda)과 슬릿 간격 d에 따른 "
            "간섭 극대 조건(d sin(theta) = m lambda)을 위치별 광강도 분포로부터 정밀 측정합니다."
        ),
        governing_equations=[
            "Single Slit Minima: a * sin(theta) = m * lambda  (m = 1, 2, ...)",
            "Double Slit Maxima: d * sin(theta) = m * lambda  (m = 0, 1, 2, ...)",
            "I(theta) = I_0 * (sin(beta)/beta)^2 * cos^2(alpha)",
            "y_m approx (m * lambda * L) / d",
        ],
        capstone_setup={
            "digital_ch_1_2": "Rotary Motion Sensor (Position, Linear Rack)",
            "analog_ch_a": "Light Sensor (Intensity, % or Lux)",
            "display": "Light Intensity vs Position Graph",
            "sampling_mode": "Continuous (Slow manual translation)",
        },
        steps=[
            ExperimentStep(
                step_index=1,
                title="광학 트랙 및 슬릿 정렬",
                instructions="레이저 광원, 슬릿 디스크, 광센서를 광학 벤치 위에 일직선으로 정렬합니다. 스크린까지의 거리 L을 측정합니다.",
                safety_notes="레이저 빔을 직접 바라보거나 반사체에 의한 반사광이 눈에 들어가지 않도록 보안경을 착용합니다.",
                capstone_action="광센서의 조리개를 좁은 슬릿(0.1mm)에 맞추고 Capstone에서 Intensity vs Position 축을 설정합니다.",
                validation_check="레이저 빔 중앙이 광센서 입사 슬릿의 정중앙을 지나도록 정밀 나사를 조절합니다.",
            ),
            ExperimentStep(
                step_index=2,
                title="단일 슬릿 회절 패턴 스캔",
                instructions="단일 슬릿(a = 0.04mm 또는 0.08mm)을 선택하고, 센서 이송대를 천천히 회전시켜 중심 피크 및 좌우 1차, 2차 극소점을 스캔합니다.",
                safety_notes="이송 핸들을 일정한 속도로 부드럽게 회전시켜 위치 노이즈를 방지합니다.",
                capstone_action="그래프 상에서 중앙 극대점과 1차 극소점 간의 거리 Delta y를 측정합니다.",
                validation_check="슬릿 폭 a = lambda * L / Delta y 공식을 적용하여 표기 슬릿 폭과 오차를 비교합니다.",
            ),
            ExperimentStep(
                step_index=3,
                title="이중 슬릿 간섭 무늬 스캔",
                instructions="이중 슬릿(d = 0.25mm, a = 0.04mm)으로 교체하고 미세 간섭 피크들이 회절 포락선 안에 나타나는 형태를 스캔합니다.",
                safety_notes="주변 조명을 끄거나 차광막을 설치하여 암실 환경을 조성합니다.",
                capstone_action="연속된 간섭 극대점들 간의 평균 간격 Delta y를 측정하여 슬릿 간격 d = lambda * L / Delta y를 도출합니다.",
                validation_check="회절 포락선 내부에 관측되는 간섭 줄무늬의 개수가 d/a 비율과 일치하는지 확인합니다.",
            ),
        ],
        quiz_questions=[
            QuizQuestion(
                question="이중 슬릿 간섭 실험에서 슬릿 간격(d)을 더 넓히면 스크린에 나타나는 간섭 줄무늬의 간격(Delta y)은 어떻게 변합니까?",
                options=[
                    "줄무늬 사이의 간격이 더 촘촘해진다 (Delta y 감소)",
                    "줄무늬 사이의 간격이 더 넓어진다 (Delta y 증가)",
                    "간격은 변하지 않고 빛의 전체 밝기만 증가한다",
                    "간섭 무늬가 완전히 사라지고 단일 회절만 남는다",
                ],
                correct_index=0,
                explanation="Delta y = (lambda * L) / d 이므로 슬릿 간격 d가 커지면 줄무늬 간격 Delta y는 반비례하여 감소합니다.",
            ),
        ],
        reference_file="0005-slit-diffraction.html",
    ),
}


def list_experiments() -> list[ExperimentCurriculum]:
    """List all available canonical physics experiment curricula."""
    return list(CANONICAL_EXPERIMENTS.values())


def get_curriculum(experiment_id: str) -> ExperimentCurriculum:
    """Retrieve curriculum for a given experiment ID.

    Args:
        experiment_id: Canonical ID (e.g. 'photoelectric_effect').

    Returns:
        ExperimentCurriculum instance.

    Raises:
        KeyError: If experiment_id is not registered.
    """
    if experiment_id not in CANONICAL_EXPERIMENTS:
        msg = f"Unknown experiment '{experiment_id}'. Available: {list(CANONICAL_EXPERIMENTS.keys())}"
        raise KeyError(msg)
    return CANONICAL_EXPERIMENTS[experiment_id]
