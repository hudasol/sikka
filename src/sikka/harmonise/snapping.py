"""Assign crash locations to registry segments by nearest centre line."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sikka.core.geo import FloatArray, point_piece_distance, project

CHUNK = 2000


@dataclass
class SegmentIndex:
    segment_ids: list[str]
    owner: np.ndarray  # index into segment_ids for every piece
    x0: FloatArray
    y0: FloatArray
    x1: FloatArray
    y1: FloatArray

    @classmethod
    def build(cls, geometries: dict[str, list[list[float]]]) -> SegmentIndex:
        ids = sorted(geometries)
        owner: list[int] = []
        xs0: list[float] = []
        ys0: list[float] = []
        xs1: list[float] = []
        ys1: list[float] = []
        for i, sid in enumerate(ids):
            coords = np.asarray(geometries[sid], dtype=np.float64)
            if coords.ndim != 2 or len(coords) < 2:
                continue
            x, y = project(coords[:, 0], coords[:, 1])
            owner += [i] * (len(coords) - 1)
            xs0 += x[:-1].tolist()
            ys0 += y[:-1].tolist()
            xs1 += x[1:].tolist()
            ys1 += y[1:].tolist()
        return cls(
            ids,
            np.asarray(owner, dtype=np.int64),
            np.asarray(xs0),
            np.asarray(ys0),
            np.asarray(xs1),
            np.asarray(ys1),
        )

    def nearest(self, lon: FloatArray, lat: FloatArray) -> tuple[list[str | None], FloatArray]:
        """Nearest segment id and distance in metres for each point."""
        n = len(lon)
        best_ids: list[str | None] = [None] * n
        best_d = np.full(n, np.inf)
        if n == 0 or len(self.owner) == 0:
            return best_ids, best_d
        px_all, py_all = project(
            np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64)
        )
        for start in range(0, n, CHUNK):
            px = px_all[start : start + CHUNK, None]
            py = py_all[start : start + CHUNK, None]
            d = point_piece_distance(px, py, self.x0, self.y0, self.x1, self.y1)
            arg = np.argmin(d, axis=1)
            best_d[start : start + CHUNK] = d[np.arange(len(arg)), arg] * 1000.0
            for k, piece in enumerate(arg):
                best_ids[start + k] = self.segment_ids[int(self.owner[piece])]
        return best_ids, best_d

    def distance_to(self, lon: float, lat: float, segment_id: str) -> float | None:
        if segment_id not in self.segment_ids:
            return None
        i = self.segment_ids.index(segment_id)
        mask = self.owner == i
        px, py = project(np.asarray([lon]), np.asarray([lat]))
        d = point_piece_distance(
            px[:, None], py[:, None], self.x0[mask], self.y0[mask], self.x1[mask], self.y1[mask]
        )
        return float(d.min() * 1000.0)
