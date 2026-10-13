import "maplibre-gl/dist/maplibre-gl.css";

import maplibregl from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import { useEffect, useRef } from "react";

export interface MapPoint {
  id: string;
  lat: number;
  lon: number;
  kind?: string;
}

interface Props {
  network: FeatureCollection | null;
  points: MapPoint[];
  label: string;
  highlight?: string | null;
}

// MapLibre with local GeoJSON only. The style has no sources with URLs, no
// glyphs and no sprites, so the map never requests tiles or fonts.
export default function MapView({ network, points, label, highlight = null }: Props) {
  const container = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!container.current || map.current) {
      return;
    }
    const css = getComputedStyle(document.documentElement);
    const color = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
    const instance = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {},
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": color("--surface", "#fbe3ea") },
          },
        ],
      },
      center: [54.0, 24.2],
      zoom: 7,
      attributionControl: false,
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => {
      instance.addSource("network", {
        type: "geojson",
        data: network ?? { type: "FeatureCollection", features: [] },
      });
      instance.addLayer({
        id: "network",
        type: "line",
        source: "network",
        paint: { "line-color": color("--ink", "#5b3a4a"), "line-width": 2 },
      });
      instance.addLayer({
        id: "network-highlight",
        type: "line",
        source: "network",
        filter: ["==", ["get", "segment_id"], highlight ?? ""],
        paint: { "line-color": color("--accent-strong", "#a8456a"), "line-width": 6 },
      });
      instance.addSource("points", { type: "geojson", data: toGeoJson(points) });
      instance.addLayer({
        id: "points",
        type: "circle",
        source: "points",
        paint: {
          "circle-radius": 4,
          "circle-color": color("--accent-strong", "#a8456a"),
          "circle-stroke-color": color("--ink", "#5b3a4a"),
          "circle-stroke-width": 1,
        },
      });
      fit(instance, network, points);
    });
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
    // The map is created once; updates are applied by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !instance.isStyleLoaded()) {
      return;
    }
    const src = instance.getSource("points") as maplibregl.GeoJSONSource | undefined;
    src?.setData(toGeoJson(points));
    const net = instance.getSource("network") as maplibregl.GeoJSONSource | undefined;
    if (network) {
      net?.setData(network);
    }
    if (instance.getLayer("network-highlight")) {
      instance.setFilter("network-highlight", ["==", ["get", "segment_id"], highlight ?? ""]);
    }
  }, [points, network, highlight]);

  return <div ref={container} className="map" role="region" aria-label={label} />;
}

function toGeoJson(points: MapPoint[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: points.map((p) => ({
      type: "Feature",
      properties: { id: p.id, kind: p.kind ?? "" },
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
    })),
  };
}

function fit(instance: maplibregl.Map, network: FeatureCollection | null, points: MapPoint[]) {
  const bounds = new maplibregl.LngLatBounds();
  let any = false;
  for (const p of points) {
    bounds.extend([p.lon, p.lat]);
    any = true;
  }
  for (const f of network?.features ?? []) {
    if (f.geometry.type === "LineString") {
      for (const c of f.geometry.coordinates) {
        bounds.extend([c[0]!, c[1]!]);
        any = true;
      }
    }
  }
  if (any) {
    instance.fitBounds(bounds, { padding: 30, animate: false });
  }
}
