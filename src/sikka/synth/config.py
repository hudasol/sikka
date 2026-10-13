"""Configuration of the synthetic world. Every number here is an assumption."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Corridor:
    code: str
    name_en: str
    name_ar: str
    road_class: str
    owner: str


# Invented corridor names. They do not correspond to any real road.
CORRIDORS: tuple[Corridor, ...] = (
    Corridor("DUN", "Dune Corridor", "ممر الكثبان", "motorway", "PRODUCER_A"),
    Corridor("PRL", "Pearl Corridor", "ممر اللؤلؤ", "motorway", "PRODUCER_C"),
    Corridor("PLM", "Palm Corridor", "ممر النخيل", "trunk", "PRODUCER_A"),
    Corridor("OAS", "Oasis Corridor", "ممر الواحة", "trunk", "PRODUCER_A"),
    Corridor("FAL", "Falcon Corridor", "ممر الصقر", "primary", "PRODUCER_C"),
    Corridor("CRL", "Coral Corridor", "ممر المرجان", "secondary", "PRODUCER_A"),
)


@dataclass(frozen=True)
class ProducerProfile:
    """How one invented producer observes and reports crashes."""

    producer_id: str
    role: str
    detection_rate: float
    coord_noise_m: float
    time_noise_min: float
    delay_median_hours: float
    delay_sigma: float
    segment_ref_share: float
    direction_share: float
    severe_only: bool
    own_corridors_only: bool
    attribute_error: float
    crash_format: str
    id_style: str


PRODUCERS: tuple[ProducerProfile, ...] = (
    ProducerProfile(
        producer_id="PRODUCER_A",
        role="road authority",
        detection_rate=0.55,
        coord_noise_m=15.0,
        time_noise_min=3.0,
        delay_median_hours=24.0,
        delay_sigma=0.8,
        segment_ref_share=0.97,
        direction_share=0.9,
        severe_only=False,
        own_corridors_only=True,
        attribute_error=0.05,
        crash_format="ndjson",
        id_style="A-{year}-{n:06d}",
    ),
    ProducerProfile(
        producer_id="PRODUCER_B",
        role="police",
        detection_rate=0.92,
        coord_noise_m=25.0,
        time_noise_min=2.0,
        delay_median_hours=2.0,
        delay_sigma=0.7,
        segment_ref_share=0.70,
        direction_share=0.8,
        severe_only=False,
        own_corridors_only=False,
        attribute_error=0.0,
        crash_format="ndjson",
        id_style="PB-{n:07d}",
    ),
    ProducerProfile(
        producer_id="PRODUCER_C",
        role="emirate level authority",
        detection_rate=0.70,
        coord_noise_m=35.0,
        time_noise_min=4.0,
        delay_median_hours=12.0,
        delay_sigma=0.8,
        segment_ref_share=0.90,
        direction_share=0.6,
        severe_only=False,
        own_corridors_only=True,
        attribute_error=0.08,
        crash_format="csv",
        id_style="C_{date}_{n:04d}",
    ),
    ProducerProfile(
        producer_id="PRODUCER_D",
        role="health sector crash reporting",
        detection_rate=0.85,
        coord_noise_m=60.0,
        time_noise_min=6.0,
        delay_median_hours=72.0,
        delay_sigma=0.6,
        segment_ref_share=0.0,
        direction_share=0.0,
        severe_only=True,
        own_corridors_only=False,
        attribute_error=0.03,
        crash_format="ndjson",
        id_style="HD-{n:06d}",
    ),
)


@dataclass(frozen=True)
class WorldConfig:
    seed: int
    segments_per_corridor: int = 40
    first_year: int = 2021
    last_year: int = 2025
    station_share: float = 0.60
    count_week_start_local: str = "2025-03-03"
    count_days: int = 7
    target_total_crashes: float = 3500.0
    n_blackspots: int = 12
    blackspot_multiplier: tuple[float, float] = (2.0, 4.0)
    spf_aadt_exponent: float = 0.85
    spf_length_exponent: float = 1.0
    spf_class_effect: dict[str, float] = field(
        default_factory=lambda: {"motorway": 0.0, "trunk": 0.15, "primary": 0.3, "secondary": 0.4}
    )
    spf_lane_effect: float = -0.05
    dispersion_k: float = 3.0
    licence: str = "Apache-2.0"

    @property
    def years(self) -> list[int]:
        return list(range(self.first_year, self.last_year + 1))
