"""Local equirectangular projection and vectorised point to polyline distances.

The synthetic network spans a few hundred kilometres, so a fixed projection
centred on it keeps distance errors around one percent, far below the buffers
used by the rules (hundreds of metres).
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

PROJ_LAT0 = 24.3
PROJ_LON0 = 54.3
KM_LAT = 110.574
KM_LON = 111.320 * math.cos(math.radians(PROJ_LAT0))

FloatArray = NDArray[np.float64]


def project(lon: FloatArray, lat: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Longitude and latitude in degrees to local x, y in kilometres."""
    return (lon - PROJ_LON0) * KM_LON, (lat - PROJ_LAT0) * KM_LAT


def unproject(x: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray]:
    return x / KM_LON + PROJ_LON0, y / KM_LAT + PROJ_LAT0


def point_piece_distance(
    px: FloatArray, py: FloatArray, x0: FloatArray, y0: FloatArray, x1: FloatArray, y1: FloatArray
) -> FloatArray:
    """Distance from points to pieces, broadcasting (points as rows, pieces as columns)."""
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    safe = np.where(length2 == 0, 1.0, length2)
    t = np.clip(((px - x0) * dx + (py - y0) * dy) / safe, 0.0, 1.0)
    t = np.where(length2 == 0, 0.0, t)
    return np.asarray(np.hypot(px - (x0 + t * dx), py - (y0 + t * dy)), dtype=np.float64)
