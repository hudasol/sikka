"""Mission exports: GeoJSON, KML and QGroundControl .plan, with a .plan validator.

The .plan structure follows the QGroundControl plan file format (version 1) as
implemented here: a mission of SimpleItem entries using MAVLink commands
NAV_TAKEOFF (22), NAV_WAYPOINT (16) and NAV_RETURN_TO_LAUNCH (20) in the
relative altitude frame (3), plus empty geofence and rally point sections.
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape

from sikka.tasking.planner import DISCLAIMER, Mission

CMD_WAYPOINT = 16
CMD_RTL = 20
CMD_TAKEOFF = 22
FRAME_RELATIVE_ALT = 3
FIRMWARE_PX4 = 12
VEHICLE_QUADROTOR = 2
ALLOWED_COMMANDS = {CMD_WAYPOINT, CMD_RTL, CMD_TAKEOFF}


def to_geojson(missions: list[Mission]) -> dict[str, Any]:
    features = []
    for m in missions:
        props = {
            "mission_id": m.mission_id,
            "segments": m.segments,
            "path_km": m.path_km,
            "flight_s": m.flight_s,
            "feasible": m.feasible,
            "disclaimer": DISCLAIMER,
            "synthetic": True,
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": m.waypoints},
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "disclaimer": DISCLAIMER, "features": features}


def to_kml(missions: list[Mission]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        "<Document>",
        "<name>Sikka survey missions (synthetic)</name>",
        f"<description>{escape(DISCLAIMER)}</description>",
    ]
    for m in missions:
        coords = " ".join(f"{lon},{lat},{alt}" for lon, lat, alt in m.waypoints)
        parts += [
            "<Placemark>",
            f"<name>{escape(m.mission_id)}</name>",
            f"<description>{escape(DISCLAIMER)}. Segments: {escape(', '.join(m.segments))}. "
            f"Flight time {m.flight_s:.0f} s.</description>",
            "<LineString><altitudeMode>relativeToGround</altitudeMode>",
            f"<coordinates>{coords}</coordinates>",
            "</LineString>",
            "</Placemark>",
        ]
    parts += ["</Document>", "</kml>"]
    return "\n".join(parts) + "\n"


def _item(jump: int, command: int, lat: float, lon: float, alt: float) -> dict[str, Any]:
    return {
        "type": "SimpleItem",
        "autoContinue": True,
        "command": command,
        "doJumpId": jump,
        "frame": FRAME_RELATIVE_ALT,
        "params": [0, 0, 0, None, lat, lon, alt],
        "Altitude": alt,
        "AltitudeMode": 1,
        "AMSLAltAboveTerrain": None,
    }


def to_plan(mission: Mission) -> dict[str, Any]:
    """One QGroundControl .plan document per mission."""
    home_lon, home_lat = mission.waypoints[0][0], mission.waypoints[0][1]
    alt = mission.waypoints[0][2]
    items = [_item(1, CMD_TAKEOFF, home_lat, home_lon, alt)]
    for i, (lon, lat, a) in enumerate(mission.waypoints[1:], start=2):
        items.append(_item(i, CMD_WAYPOINT, lat, lon, a))
    items.append(
        {
            "type": "SimpleItem",
            "autoContinue": True,
            "command": CMD_RTL,
            "doJumpId": len(items) + 1,
            "frame": 2,
            "params": [0, 0, 0, 0, 0, 0, 0],
        }
    )
    profile = mission.metadata.get("profile", {})
    return {
        "fileType": "Plan",
        "version": 1,
        "groundStation": "QGroundControl",
        "geoFence": {"circles": [], "polygons": [], "version": 2},
        "rallyPoints": {"points": [], "version": 2},
        "mission": {
            "version": 2,
            "firmwareType": FIRMWARE_PX4,
            "vehicleType": VEHICLE_QUADROTOR,
            "cruiseSpeed": profile.get("speed_mps", 12.0),
            "hoverSpeed": 5,
            "globalPlanAltitudeMode": 1,
            "plannedHomePosition": [home_lat, home_lon, 0],
            "items": items,
        },
        "sikka": {"mission_id": mission.mission_id, "disclaimer": DISCLAIMER, "synthetic": True},
    }


def validate_plan(plan: Any) -> list[str]:
    """Return a list of problems; an empty list means the plan is structurally valid."""
    errors: list[str] = []

    def need(cond: bool, message: str) -> None:
        if not cond:
            errors.append(message)

    need(isinstance(plan, dict), "plan must be an object")
    if not isinstance(plan, dict):
        return errors
    need(plan.get("fileType") == "Plan", "fileType must be Plan")
    need(plan.get("version") == 1, "version must be 1")
    need(plan.get("groundStation") == "QGroundControl", "groundStation must be QGroundControl")
    for section in ("geoFence", "rallyPoints"):
        need(
            isinstance(plan.get(section), dict) and plan[section].get("version") == 2,
            f"{section} must be an object with version 2",
        )
    mission = plan.get("mission")
    need(isinstance(mission, dict), "mission must be an object")
    if not isinstance(mission, dict):
        return errors
    need(mission.get("version") == 2, "mission.version must be 2")
    need(isinstance(mission.get("firmwareType"), int), "mission.firmwareType must be an integer")
    need(isinstance(mission.get("vehicleType"), int), "mission.vehicleType must be an integer")
    need(
        isinstance(mission.get("cruiseSpeed"), int | float) and mission["cruiseSpeed"] > 0,
        "mission.cruiseSpeed must be positive",
    )
    home = mission.get("plannedHomePosition")
    need(isinstance(home, list) and len(home) == 3, "plannedHomePosition must be [lat, lon, alt]")
    items = mission.get("items")
    need(isinstance(items, list) and len(items) >= 3, "mission needs take off, waypoints and RTL")
    if not isinstance(items, list) or not items:
        return errors
    need(items[0].get("command") == CMD_TAKEOFF, "first item must be NAV_TAKEOFF (22)")
    need(items[-1].get("command") == CMD_RTL, "last item must be NAV_RETURN_TO_LAUNCH (20)")
    last_jump = 0
    for n, item in enumerate(items):
        where = f"item {n + 1}"
        need(item.get("type") == "SimpleItem", f"{where}: type must be SimpleItem")
        need(item.get("command") in ALLOWED_COMMANDS, f"{where}: unsupported command")
        jump = item.get("doJumpId")
        need(isinstance(jump, int) and jump > last_jump, f"{where}: doJumpId must increase")
        last_jump = jump if isinstance(jump, int) else last_jump
        params = item.get("params")
        need(isinstance(params, list) and len(params) == 7, f"{where}: params must have 7 values")
        need(isinstance(item.get("autoContinue"), bool), f"{where}: autoContinue must be boolean")
        positional = isinstance(params, list) and len(params) == 7
        if item.get("command") in {CMD_TAKEOFF, CMD_WAYPOINT} and positional:
            lat, lon, alt = params[4], params[5], params[6]
            need(isinstance(lat, int | float) and -90 <= lat <= 90, f"{where}: latitude range")
            need(isinstance(lon, int | float) and -180 <= lon <= 180, f"{where}: longitude range")
            need(isinstance(alt, int | float) and 0 < alt <= 120, f"{where}: altitude 0 to 120 m")
            need(item.get("frame") == FRAME_RELATIVE_ALT, f"{where}: frame must be 3")
    return errors
