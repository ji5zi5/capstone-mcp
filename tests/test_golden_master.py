# Copyright 2026 Capstone MCP contributors.
"""Golden master tests validating bounded decoding against real Capstone archives."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest

from capstone_mcp.capfile_models import CapFile, CapValueKind
from capstone_mcp.capfiles import (
    extract_cap_datasets,
    read_cap_configuration,
    read_cap_file,
)

GOLDEN_MASTER_DIR: Final = Path(
    os.environ.get(
        "CAPSTONE_GOLDEN_MASTER_DIR",
        r"C:\Users\Jio\Downloads\(2026)캡스톤 실험별 파일",
    ),
)

pytestmark = pytest.mark.skipif(
    not GOLDEN_MASTER_DIR.exists(),
    reason=f"Golden master Capstone archives not found at {GOLDEN_MASTER_DIR}",
)

ARCHIVES_BY_DOMAIN: Final[dict[str, list[str]]] = {
    "Optics": [
        "[광학]빛의 간섭과 회절(EX-5545A, 550, CI-6504)[1].cap",
        "[광학]빛의 편광(OS-8441, PS-3220)[3].cap",
        "[광학]빛의 회절과 간섭(OS-8441, 8439, CS)[1].cap",
        "Polarization of Light w  Data(Wireless)[3].cap",
    ],
    "Mechanics": [
        "[역학]강제 조화 진동(EX-5551A, Smart Cart, CS)[5].cap",
        "[역학]회전관성 실험(EX-5516A, 550, CS)[7].cap",
        "자이로스코프(ME-8960, 850, CS, PS-2120A, PS-3220)[6].cap",
    ],
    "Thermodynamics": [
        "[열역학]EX-5530 Heat Engine Cycle with videos.cap",
        "[열역학]단열 기체 법칙(TD-8565, 850)[13].cap",
    ],
    "Electromagnetism": [
        "[전자기]전기회로(EM-8656, 850, CS)[8].cap",
    ],
    "Modern Physics": [
        "[현대물리]광전효과(EX-5549A, 850, CS)[9].cap",
        "[현대물리]흑체복사(EX-5529A, 850, CS)[12].cap",
    ],
}

ALL_ARCHIVES: Final[list[tuple[str, str]]] = [
    (domain, filename)
    for domain, files in ARCHIVES_BY_DOMAIN.items()
    for filename in files
]

ARCHIVES_WITH_DATASETS: Final[list[str]] = [
    "[광학]빛의 간섭과 회절(EX-5545A, 550, CI-6504)[1].cap",
    "[역학]강제 조화 진동(EX-5551A, Smart Cart, CS)[5].cap",
    "[열역학]단열 기체 법칙(TD-8565, 850)[13].cap",
    "[전자기]전기회로(EM-8656, 850, CS)[8].cap",
    "[현대물리]광전효과(EX-5549A, 850, CS)[9].cap",
    "[현대물리]흑체복사(EX-5529A, 850, CS)[12].cap",
    "Polarization of Light w  Data(Wireless)[3].cap",
    "자이로스코프(ME-8960, 850, CS, PS-2120A, PS-3220)[6].cap",
]


def _signal_names(cap: CapFile) -> set[str]:
    names: set[str] = set()
    for source in cap.data_sources:
        for name in (
            source.measurement_name,
            source.long_name,
            source.short_name,
            source.symbol_name,
        ):
            if name:
                names.add(name)
    return names


def _sensor_names(cap: CapFile) -> set[str]:
    return {
        sensor.name
        for interface in cap.hardware_interfaces
        for sensor in interface.sensors
        if sensor.name
    }


def test_golden_master_catalog_discovery() -> None:
    found_cap_files = {p.name for p in GOLDEN_MASTER_DIR.glob("*.cap")}
    expected_files = {filename for _, filename in ALL_ARCHIVES}
    assert expected_files.issubset(found_cap_files)
    assert len(expected_files) == 12
    assert len(ARCHIVES_BY_DOMAIN["Optics"]) == 4
    assert len(ARCHIVES_BY_DOMAIN["Mechanics"]) == 3
    assert len(ARCHIVES_BY_DOMAIN["Thermodynamics"]) == 2
    assert len(ARCHIVES_BY_DOMAIN["Electromagnetism"]) == 1
    assert len(ARCHIVES_BY_DOMAIN["Modern Physics"]) == 2


@pytest.mark.parametrize(("domain", "filename"), ALL_ARCHIVES)
def test_golden_master_decodability_and_metadata(
    domain: str,
    filename: str,
) -> None:
    assert domain in ARCHIVES_BY_DOMAIN
    archive_path = GOLDEN_MASTER_DIR / filename
    cap = read_cap_file(archive_path)

    assert cap.file_name == filename
    assert cap.root_tag == "DSProExperiment"
    assert cap.header is not None
    assert "Version" in cap.header.attributes
    assert cap.hardware is not None
    assert cap.workspace is not None
    assert cap.calculations is not None
    assert len(cap.experiment_settings) >= 1
    assert len(cap.data_sources) >= 18

    configuration = read_cap_configuration(archive_path)
    assert configuration.file_name == filename
    assert len(configuration.data_sources) == len(cap.data_sources)
    assert len(configuration.experiment_settings) == len(cap.experiment_settings)

    datasets = extract_cap_datasets(archive_path)
    assert len(datasets) == len(cap.datasets)


def test_golden_master_record_type_0_empty_records() -> None:
    archive_path = (
        GOLDEN_MASTER_DIR
        / "[광학]빛의 간섭과 회절(EX-5545A, 550, CI-6504)[1].cap"
    )
    cap = read_cap_file(archive_path)

    datasets_by_source = {ds.source_name: ds for ds in cap.datasets}
    assert "d" in datasets_by_source
    assert "n" in datasets_by_source

    ds_d = datasets_by_source["d"]
    assert len(ds_d.raw_values) == 10
    assert ds_d.raw_values[:4] == ["", "", "", ""]
    assert ds_d.numeric_values is not None
    assert ds_d.numeric_values[:4] == [None, None, None, None]
    assert ds_d.numeric_values[4:] == [
        Decimal("0.00025"),
        Decimal("0.00025"),
        Decimal("0.0005"),
        Decimal("0.0005"),
        Decimal("0.0005"),
        Decimal("0.0005"),
    ]
    assert ds_d.unit_id == 1280

    ds_n = datasets_by_source["n"]
    assert len(ds_n.raw_values) == 10
    assert ds_n.raw_values[:4] == ["", "", "", ""]
    assert ds_n.numeric_values is not None
    assert ds_n.numeric_values[:4] == [None, None, None, None]
    assert ds_n.numeric_values[4:] == [
        Decimal(5),
        Decimal(13),
        Decimal(12),
        Decimal(27),
        Decimal(5),
        Decimal(12),
    ]
    assert ds_n.unit_id == 0

    assert "left x" in datasets_by_source
    ds_left_x = datasets_by_source["left x"]
    assert len(ds_left_x.raw_values) == 0
    assert ds_left_x.numeric_values is None

    assert "del x" in datasets_by_source
    ds_del_x = datasets_by_source["del x"]
    assert len(ds_del_x.raw_values) == 4
    assert ds_del_x.raw_values.count("") == 0
    assert ds_del_x.numeric_values is not None
    assert None not in ds_del_x.numeric_values


def test_golden_master_signals_optics() -> None:
    pol_path = (
        GOLDEN_MASTER_DIR
        / "Polarization of Light w  Data(Wireless)[3].cap"
    )
    cap_pol = read_cap_file(pol_path)
    pol_signals = _signal_names(cap_pol)
    expected_pol_signals = {
        "Light Intensity",
        "Log of Light Intensity",
        "Angle",
        "Angular Velocity",
        "Angular Acceleration",
        "Position",
        "Velocity",
        "Acceleration",
    }
    assert expected_pol_signals.issubset(pol_signals)

    interf_path = (
        GOLDEN_MASTER_DIR
        / "[광학]빛의 간섭과 회절(EX-5545A, 550, CI-6504)[1].cap"
    )
    cap_interf = read_cap_file(interf_path)
    interf_signals = _signal_names(cap_interf)
    assert {"Speed of light", "Electron charge", "del x"}.issubset(interf_signals)

    optics_sensors = _sensor_names(cap_pol)
    assert {
        "Diffraction Position Sensor",
        "Diffraction Intensity Sensor",
        "Wireless Rotary Motion Sensor",
    }.issubset(optics_sensors)


def test_golden_master_signals_mechanics() -> None:
    harmonic_path = (
        GOLDEN_MASTER_DIR
        / "[역학]강제 조화 진동(EX-5551A, Smart Cart, CS)[5].cap"
    )
    cap_harmonic = read_cap_file(harmonic_path)
    harmonic_signals = _signal_names(cap_harmonic)
    assert {
        "Output Voltage",
        "Output Current",
        "Spring Constant",
    }.issubset(harmonic_signals)
    harmonic_sensors = _sensor_names(cap_harmonic)
    assert {
        "Output Voltage-Current Sensor",
        "Smart Cart Force Sensor",
        "Smart Cart Position Sensor",
    }.issubset(harmonic_sensors)

    gyro_path = (
        GOLDEN_MASTER_DIR
        / "자이로스코프(ME-8960, 850, CS, PS-2120A, PS-3220)[6].cap"
    )
    cap_gyro = read_cap_file(gyro_path)
    gyro_signals = _signal_names(cap_gyro)
    assert {
        "Angle",
        "Angular Velocity",
        "Angular Acceleration",
        "Position",
        "Velocity",
        "Acceleration",
    }.issubset(gyro_signals)

    inertia_path = (
        GOLDEN_MASTER_DIR
        / "[역학]회전관성 실험(EX-5516A, 550, CS)[7].cap"
    )
    cap_inertia = read_cap_file(inertia_path)
    inertia_sensors = _sensor_names(cap_inertia)
    assert "Rotary Motion Sensor" in inertia_sensors


def test_golden_master_signals_thermodynamics() -> None:
    engine_path = (
        GOLDEN_MASTER_DIR
        / "[열역학]EX-5530 Heat Engine Cycle with videos.cap"
    )
    cap_engine = read_cap_file(engine_path)
    engine_sensors = _sensor_names(cap_engine)
    assert {
        "Rotary Motion Sensor",
        "Dual Pressure Sensor",
        "Temperature Sensor, Quad",
    }.issubset(engine_sensors)

    gas_path = (
        GOLDEN_MASTER_DIR
        / "[열역학]단열 기체 법칙(TD-8565, 850)[13].cap"
    )
    cap_gas = read_cap_file(gas_path)
    gas_signals = _signal_names(cap_gas)
    assert {"Voltage", "Current Probe (PS-2184)", "h cal"}.issubset(gas_signals)


def test_golden_master_signals_electromagnetism() -> None:
    em_path = (
        GOLDEN_MASTER_DIR
        / "[전자기]전기회로(EM-8656, 850, CS)[8].cap"
    )
    cap_em = read_cap_file(em_path)
    em_signals = _signal_names(cap_em)
    assert {
        "Voltage",
        "Zero Current",
        "Measured Current",
        "voltage",
    }.issubset(em_signals)
    em_sensors = _sensor_names(cap_em)
    assert {
        "Voltage Sensor",
        "Output Voltage-Current Sensor",
    }.issubset(em_sensors)


def test_golden_master_signals_modern_physics() -> None:
    photo_path = (
        GOLDEN_MASTER_DIR
        / "[현대물리]광전효과(EX-5549A, 850, CS)[9].cap"
    )
    cap_photo = read_cap_file(photo_path)
    photo_signals = _signal_names(cap_photo)
    assert {
        "Frequency",
        "Stopping Voltage",
        "Aperture",
        "Wavelength",
        "Current",
        "Voltage",
    }.issubset(photo_signals)

    blackbody_path = (
        GOLDEN_MASTER_DIR
        / "[현대물리]흑체복사(EX-5529A, 850, CS)[12].cap"
    )
    cap_blackbody = read_cap_file(blackbody_path)
    bb_signals = _signal_names(cap_blackbody)
    assert {
        "Table Angle",
        "Shaft Angle",
        "Index of Refraction",
        "Wavelength",
        "Lambda",
        "rho",
        "T",
        "R hold",
    }.issubset(bb_signals)


@pytest.mark.parametrize(("domain", "filename"), ALL_ARCHIVES)
def test_golden_master_physical_units(domain: str, filename: str) -> None:
    assert domain in ARCHIVES_BY_DOMAIN
    archive_path = GOLDEN_MASTER_DIR / filename
    cap = read_cap_file(archive_path)

    known_unit_ids = {
        -1,  # Raw / uncalibrated
        0,  # Dimensionless / count / text
        256,  # Volts alt
        512,  # Temperature (Celsius)
        514,  # Temperature (Kelvin)
        770,  # Pressure (kPa)
        1024,  # Potential (Volts)
        1280,  # Distance / Position (Meters)
        1282,  # Distance (Millimeters)
        1536,  # Magnetic Field (Tesla/Gauss)
        2048,  # Acceleration (m/s^2)
        2049,  # Acceleration alt
        2304,  # Velocity (m/s)
        2560,  # Angle (Radians)
        2561,  # Angle (Degrees)
        2816,  # Angular Velocity (rad/s)
        2817,  # Angular Velocity base unit (deg/s or rev/s)
        3072,  # Angular Acceleration (rad/s^2)
        3330,  # Time (Seconds)
        3584,  # Current (Amperes)
        4352,  # Resistance (Ohms)
        5122,  # Illuminance (lux)
        5376,  # Relative Intensity (%)
        7936,  # Frequency (Hz)
        10496,  # Force (Newtons)
        10752,  # Energy / Work (Joules)
        10753,  # Energy alt
        32768,  # User / Custom calculation unit
    }

    source_by_euid = {s.euid: s for s in cap.data_sources}

    for source in cap.data_sources:
        if source.default_unit_id is not None:
            assert isinstance(source.default_unit_id, int)
            assert source.default_unit_id in known_unit_ids
        if source.base_unit_id is not None:
            assert isinstance(source.base_unit_id, int)
            assert source.base_unit_id in known_unit_ids

    for ds in cap.datasets:
        source = source_by_euid.get(ds.source_euid)
        assert source is not None
        assert ds.unit_id == source.default_unit_id
        if ds.unit_id is not None:
            assert ds.unit_id in known_unit_ids


@pytest.mark.parametrize("filename", ARCHIVES_WITH_DATASETS)
def test_golden_master_dataset_integrity(filename: str) -> None:
    archive_path = GOLDEN_MASTER_DIR / filename
    cap = read_cap_file(archive_path)
    assert len(cap.datasets) > 0

    for ds in cap.datasets:
        count = len(ds.raw_values)
        assert len(ds.sample_indices) == count
        assert ds.sample_indices == list(range(count))
        assert len(ds.independent_values) == count
        assert ds.independent_kind in {"index", "interval", "stored"}
        assert ds.value_kind in {
            CapValueKind.NUMERIC,
            CapValueKind.TEXT,
            CapValueKind.UNKNOWN,
        }

        if ds.numeric_values is not None:
            assert len(ds.numeric_values) == count
            for raw, num in zip(ds.raw_values, ds.numeric_values, strict=True):
                if raw == "":
                    assert num is None
                else:
                    assert isinstance(num, Decimal)


def test_golden_master_run_labels_wireless_polarization() -> None:
    archive_path = (
        GOLDEN_MASTER_DIR
        / "Polarization of Light w  Data(Wireless)[3].cap"
    )
    cap = read_cap_file(archive_path)
    assert len(cap.datasets) == 16

    runs = {ds.run_name for ds in cap.datasets}
    assert runs == {"Run #1", "Run #2"}

    run_1_datasets = [ds for ds in cap.datasets if ds.run_name == "Run #1"]
    run_2_datasets = [ds for ds in cap.datasets if ds.run_name == "Run #2"]
    assert len(run_1_datasets) == 8
    assert len(run_2_datasets) == 8

    for ds in run_1_datasets:
        assert len(ds.raw_values) in (1239, 1242, 1244)
    for ds in run_2_datasets:
        assert len(ds.raw_values) in (458, 461, 462, 463)


def test_golden_master_run_labels_gyroscope() -> None:
    archive_path = (
        GOLDEN_MASTER_DIR
        / "자이로스코프(ME-8960, 850, CS, PS-2120A, PS-3220)[6].cap"
    )
    cap = read_cap_file(archive_path)
    assert len(cap.datasets) == 36

    runs = {ds.run_name for ds in cap.datasets}
    assert runs == {"Run #1", "Run #2", "Run #3"}

    for run_name in ("Run #1", "Run #2", "Run #3"):
        run_datasets = [ds for ds in cap.datasets if ds.run_name == run_name]
        assert len(run_datasets) == 12
        for ds in run_datasets:
            assert len(ds.raw_values) > 500
