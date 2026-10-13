"""Contract v1.0.0 models. The single source of truth for every generated artefact.

Each field carries an English description, an Arabic description (machine
drafted, pending review by a native speaker), a unit where one applies and an
example. Optional fields are absent when missing: an explicit ``null`` is
rejected, as are sentinel values, by the conformance rules.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from sikka.contract.conventions import IDENTIFIER_PATTERN, SEMVER_PATTERN, UTC_TIMESTAMP_PATTERN

Identifier = Annotated[str, StringConstraints(pattern=IDENTIFIER_PATTERN)]
UtcTimestamp = Annotated[str, StringConstraints(pattern=UTC_TIMESTAMP_PATTERN)]

FeedType = Literal["road_segments", "crash_records", "traffic_counts"]
RoadClass = Literal["motorway", "trunk", "primary", "secondary"]
Direction = Literal["both", "forward", "reverse"]
CrashDirection = Literal["forward", "reverse"]
Severity = Literal["fatal", "serious_injury", "minor_injury", "property_damage_only"]
CollisionType = Literal[
    "rear_end",
    "side_impact",
    "head_on",
    "rollover",
    "run_off_road",
    "pedestrian",
    "fixed_object",
    "other",
]
ContributingFactor = Literal[
    "speeding",
    "tailgating",
    "sudden_swerving",
    "fatigue",
    "distraction",
    "mechanical_failure",
    "weather",
    "other",
]
Weather = Literal["clear", "rain", "fog", "dust_sand", "strong_wind", "other"]
LightCondition = Literal["daylight", "dark_lit", "dark_unlit", "dawn_dusk"]
RoadSurface = Literal["dry", "wet", "sand_covered", "damaged", "other"]
QualityFlag = Literal["ok", "estimated", "suspect"]


def describe(
    en: str,
    ar: str,
    *,
    example: Any,
    unit: str | None = None,
    **constraints: Any,
) -> Any:
    """Field with bilingual description, unit and example in the JSON Schema."""
    extra: dict[str, Any] = {"x-description-ar": ar}
    if unit is not None:
        extra["x-unit"] = unit
    return Field(description=en, examples=[example], json_schema_extra=extra, **constraints)


class ContractModel(BaseModel):
    """Base for every contract model: unknown fields and explicit nulls are refused."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=False)

    @model_validator(mode="before")
    @classmethod
    def _absent_not_null(cls, data: Any) -> Any:
        if isinstance(data, dict):
            nulls = sorted(k for k, v in data.items() if v is None)
            if nulls:
                raise ValueError(f"missing values must be absent, not null: {nulls}")
        return data


class ProvenanceHeader(ContractModel):
    """Header that starts every feed file."""

    producer_id: Identifier = describe(
        "Identifier of the producer that generated the feed.",
        "معرّف الجهة المنتجة التي أعدّت ملف البيانات.",
        example="PRODUCER_A",
    )
    feed_type: FeedType = describe(
        "Which of the three contract feeds this file contains.",
        "نوع ملف البيانات من بين الأنواع الثلاثة المحددة في العقد.",
        example="crash_records",
    )
    contract_version: str = describe(
        "Contract version the file claims to follow, as MAJOR.MINOR.PATCH.",
        "إصدار العقد الذي يلتزم به الملف بصيغة رئيسي.فرعي.تصحيح.",
        example="1.0.0",
        pattern=SEMVER_PATTERN,
    )
    generated_at: UtcTimestamp = describe(
        "When the producer generated the file, in UTC.",
        "وقت إعداد الملف لدى الجهة المنتجة بالتوقيت العالمي المنسق.",
        example="2026-01-05T08:00:00Z",
    )
    licence: str = describe(
        "Licence under which the records may be used.",
        "الترخيص الذي يحكم استخدام السجلات.",
        example="Apache-2.0",
        min_length=1,
    )
    synthetic: bool = describe(
        "True when every record in the file is synthetic. Must be true in this repository.",
        "تكون القيمة صحيحة عندما تكون جميع السجلات مصطنعة. يجب أن تكون صحيحة في هذا المستودع.",
        example=True,
    )
    record_count: int = describe(
        "Number of records that follow the header.",
        "عدد السجلات التي تلي الترويسة.",
        example=1250,
        unit="records",
        ge=0,
    )
    period_start: UtcTimestamp = describe(
        "Start of the period the records cover, in UTC, inclusive.",
        "بداية الفترة التي تغطيها السجلات بالتوقيت العالمي المنسق، شاملة.",
        example="2021-01-01T00:00:00Z",
    )
    period_end: UtcTimestamp = describe(
        "End of the period the records cover, in UTC, exclusive.",
        "نهاية الفترة التي تغطيها السجلات بالتوقيت العالمي المنسق، غير شاملة.",
        example="2026-01-01T00:00:00Z",
    )


class LineStringGeometry(ContractModel):
    """GeoJSON LineString in WGS84, longitude first."""

    type: Literal["LineString"] = describe(
        "GeoJSON geometry type. Always LineString.",
        "نوع الشكل الهندسي وفق GeoJSON، وهو دائما LineString.",
        example="LineString",
    )
    coordinates: list[tuple[float, float]] = describe(
        "Ordered positions as [lon, lat] pairs in decimal degrees.",
        "مواقع مرتبة على شكل أزواج [خط الطول، خط العرض] بالدرجات العشرية.",
        example=[[54.40, 24.45], [54.41, 24.46]],
        unit="degrees",
        min_length=2,
    )


class RoadSegment(ContractModel):
    """Feed 1: one row of the road segment registry."""

    segment_id: Identifier = describe(
        "Stable identifier of the road segment.",
        "معرّف ثابت لمقطع الطريق.",
        example="SEG-C1-001",
    )
    road_name_en: str = describe(
        "Road name in English.",
        "اسم الطريق باللغة الإنجليزية.",
        example="Corridor One",
        min_length=1,
    )
    road_name_ar: str = describe(
        "Road name in Arabic.",
        "اسم الطريق باللغة العربية.",
        example="الممر الأول",
        min_length=1,
    )
    road_class: RoadClass = describe(
        "Functional class of the road.",
        "التصنيف الوظيفي للطريق.",
        example="motorway",
    )
    length_m: float = describe(
        "Segment length along the centre line.",
        "طول المقطع على امتداد خط المنتصف.",
        example=4200.0,
        unit="m",
        gt=0,
    )
    lane_count: int = describe(
        "Number of through lanes in the direction(s) covered.",
        "عدد المسارات المستمرة في الاتجاه أو الاتجاهات المشمولة.",
        example=4,
        unit="lanes",
        ge=1,
        le=12,
    )
    speed_limit_kmh: int = describe(
        "Posted speed limit.",
        "الحد الأقصى المعلن للسرعة.",
        example=120,
        unit="km/h",
        ge=20,
        le=160,
    )
    direction: Direction = describe(
        "Traffic direction the segment row describes.",
        "اتجاه حركة المرور الذي يصفه سجل المقطع.",
        example="both",
    )
    owner_producer_id: Identifier = describe(
        "Producer responsible for maintaining this segment record.",
        "الجهة المنتجة المسؤولة عن تحديث سجل هذا المقطع.",
        example="PRODUCER_A",
    )
    geometry: LineStringGeometry = describe(
        "Centre line geometry as a GeoJSON LineString.",
        "الشكل الهندسي لخط المنتصف بصيغة GeoJSON LineString.",
        example={"type": "LineString", "coordinates": [[54.40, 24.45], [54.41, 24.46]]},
    )
    valid_from: UtcTimestamp = describe(
        "Start of validity of this segment definition, in UTC.",
        "بداية سريان تعريف هذا المقطع بالتوقيت العالمي المنسق.",
        example="2020-01-01T00:00:00Z",
    )
    valid_to: UtcTimestamp | None = describe(
        "End of validity, in UTC. Absent while the definition is current.",
        "نهاية سريان التعريف بالتوقيت العالمي المنسق. يُحذف الحقل ما دام التعريف ساريا.",
        example="2027-01-01T00:00:00Z",
        default=None,
    )


class CrashRecord(ContractModel):
    """Feed 2: one reported crash. No free text fields are allowed."""

    crash_id: Identifier = describe(
        "Identifier of the crash within the producer's feed.",
        "معرّف الحادث ضمن ملف الجهة المنتجة.",
        example="B-2023-000123",
    )
    producer_id: Identifier = describe(
        "Producer that reported the crash.",
        "الجهة المنتجة التي أبلغت عن الحادث.",
        example="PRODUCER_B",
    )
    occurred_at: UtcTimestamp = describe(
        "When the crash occurred, in UTC.",
        "وقت وقوع الحادث بالتوقيت العالمي المنسق.",
        example="2023-05-14T17:42:00Z",
    )
    reported_at: UtcTimestamp = describe(
        "When the record entered the producer's system, in UTC.",
        "وقت إدخال السجل في نظام الجهة المنتجة بالتوقيت العالمي المنسق.",
        example="2023-05-14T19:05:00Z",
    )
    lat: float = describe(
        "Latitude of the crash location, WGS84.",
        "خط عرض موقع الحادث وفق WGS84.",
        example=24.4521,
        unit="degrees",
        ge=-90,
        le=90,
    )
    lon: float = describe(
        "Longitude of the crash location, WGS84.",
        "خط طول موقع الحادث وفق WGS84.",
        example=54.4033,
        unit="degrees",
        ge=-180,
        le=180,
    )
    segment_ref: Identifier | None = describe(
        "Segment the producer assigned the crash to, if any.",
        "المقطع الذي نسبت إليه الجهة المنتجة الحادث، إن وجد.",
        example="SEG-C1-001",
        default=None,
    )
    direction: CrashDirection | None = describe(
        "Travel direction of the first vehicle relative to the segment, if known.",
        "اتجاه سير المركبة الأولى بالنسبة إلى المقطع، إن كان معروفا.",
        example="forward",
        default=None,
    )
    severity: Severity = describe(
        "Most severe injury outcome of the crash.",
        "أشد نتيجة إصابة نتجت عن الحادث.",
        example="minor_injury",
    )
    vehicles_involved: int = describe(
        "Number of vehicles involved.",
        "عدد المركبات المشاركة في الحادث.",
        example=2,
        unit="vehicles",
        ge=1,
        le=20,
    )
    collision_type: CollisionType = describe(
        "Manner of collision.",
        "نوع التصادم.",
        example="rear_end",
    )
    contributing_factors: list[ContributingFactor] = describe(
        "Coded contributing factors. Empty list when none were coded.",
        "العوامل المساهمة المرمّزة. قائمة فارغة إذا لم يُرمّز أي عامل.",
        example=["tailgating"],
        max_length=8,
    )
    weather: Weather = describe(
        "Weather at the time of the crash.",
        "حالة الطقس وقت وقوع الحادث.",
        example="clear",
    )
    light_condition: LightCondition = describe(
        "Light condition at the time of the crash.",
        "حالة الإضاءة وقت وقوع الحادث.",
        example="daylight",
    )
    road_surface: RoadSurface = describe(
        "Road surface condition at the time of the crash.",
        "حالة سطح الطريق وقت وقوع الحادث.",
        example="dry",
    )


class ClassCounts(ContractModel):
    """Vehicle counts by class within one interval."""

    car: int | None = describe(
        "Passenger cars.", "السيارات الخاصة.", example=410, unit="vehicles", ge=0, default=None
    )
    light_goods: int | None = describe(
        "Light goods vehicles.",
        "مركبات نقل البضائع الخفيفة.",
        example=60,
        unit="vehicles",
        ge=0,
        default=None,
    )
    heavy_goods: int | None = describe(
        "Heavy goods vehicles.",
        "مركبات نقل البضائع الثقيلة.",
        example=35,
        unit="vehicles",
        ge=0,
        default=None,
    )
    bus: int | None = describe(
        "Buses and coaches.", "الحافلات.", example=8, unit="vehicles", ge=0, default=None
    )
    motorcycle: int | None = describe(
        "Motorcycles.", "الدراجات النارية.", example=3, unit="vehicles", ge=0, default=None
    )


class TrafficCount(ContractModel):
    """Feed 3: one interval from one traffic counting station."""

    station_id: Identifier = describe(
        "Identifier of the counting station.",
        "معرّف محطة العد المروري.",
        example="STN-C1-004",
    )
    segment_ref: Identifier = describe(
        "Segment the station measures.",
        "المقطع الذي تقيسه المحطة.",
        example="SEG-C1-004",
    )
    interval_start: UtcTimestamp = describe(
        "Start of the counting interval, in UTC.",
        "بداية فترة العد بالتوقيت العالمي المنسق.",
        example="2024-02-01T06:00:00Z",
    )
    interval_minutes: int = describe(
        "Length of the counting interval.",
        "طول فترة العد.",
        example=15,
        unit="min",
        ge=1,
        le=60,
    )
    vehicle_count: int = describe(
        "Vehicles counted in the interval, all classes and lanes.",
        "عدد المركبات المحسوبة في الفترة لجميع الفئات والمسارات.",
        example=516,
        unit="vehicles",
        ge=0,
    )
    mean_speed_kmh: float = describe(
        "Mean spot speed of counted vehicles.",
        "متوسط السرعة اللحظية للمركبات المحسوبة.",
        example=104.5,
        unit="km/h",
        ge=0,
        le=250,
    )
    occupancy_pct: float = describe(
        "Share of the interval the detector was occupied.",
        "نسبة زمن الفترة التي كان فيها الكاشف مشغولا.",
        example=7.5,
        unit="%",
        ge=0,
        le=100,
    )
    class_counts: ClassCounts | None = describe(
        "Counts by vehicle class, when the station classifies vehicles.",
        "أعداد المركبات حسب الفئة، عندما تصنّف المحطة المركبات.",
        example={"car": 410, "light_goods": 60, "heavy_goods": 35, "bus": 8, "motorcycle": 3},
        default=None,
    )
    quality_flag: QualityFlag = describe(
        "Producer's own quality flag for the interval.",
        "مؤشر الجودة الذي تضعه الجهة المنتجة للفترة.",
        example="ok",
    )


FEED_MODELS: dict[str, type[ContractModel]] = {
    "road_segments": RoadSegment,
    "crash_records": CrashRecord,
    "traffic_counts": TrafficCount,
}
