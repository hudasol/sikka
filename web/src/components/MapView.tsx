import "maplibre-gl/dist/maplibre-gl.css";

import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { FeatureCollection } from "geojson";
import { useEffect, useRef } from "react";

// MapLibre 6 runs its parsing in a module worker shipped as a separate file.
// Vite copies it into the build through the ?url import; without this the
// worker URL falls back to the page and nothing is drawn.
maplibregl.setWorkerUrl(workerUrl);

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
  onSelectSegment?: (segmentId: string) => void;
  routes?: FeatureCollection | null;
}

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

interface Latest {
  network: FeatureCollection | null;
  points: MapPoint[];
  routes: FeatureCollection | null;
  highlight: string | null;
  select?: (segmentId: string) => void;
}

// MapLibre with local GeoJSON only. The style has no sources with URLs, no
// glyphs and no sprites, so the map never requests tiles or fonts. Data that
// arrives after the map was created is applied as soon as the style has loaded.
export default function MapView({
  network,
  points,
  label,
  highlight = null,
  onSelectSegment,
  routes = null,
}: Props) {
  const container = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const loaded = useRef(false);
  const fitted = useRef(false);
  const latest = useRef<Latest>({ network, points, routes, highlight });
  latest.current = { network, points, routes, highlight, select: onSelectSegment };

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
        sources: {
          network: { type: "geojson", data: EMPTY },
          routes: { type: "geojson", data: EMPTY },
          points: { type: "geojson", data: EMPTY },
        },
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": color("--surface", "#fbe3ea") },
          },
          {
            id: "network",
            type: "line",
            source: "network",
            paint: { "line-color": color("--ink", "#5b3a4a"), "line-width": 2 },
          },
          {
            id: "network-highlight",
            type: "line",
            source: "network",
            filter: ["==", ["get", "segment_id"], ""],
            paint: { "line-color": color("--accent-strong", "#a8456a"), "line-width": 7 },
          },
          {
            id: "routes",
            type: "line",
            source: "routes",
            paint: {
              "line-color": color("--accent-strong", "#a8456a"),
              "line-width": 4,
              "line-dasharray": [2, 1],
            },
          },
          {
            id: "points",
            type: "circle",
            source: "points",
            paint: {
              "circle-radius": 4,
              "circle-color": color("--accent-strong", "#a8456a"),
              "circle-stroke-color": color("--ink", "#5b3a4a"),
              "circle-stroke-width": 1,
            },
          },
        ],
      },
      center: [54.0, 24.2],
      zoom: 7,
      attributionControl: false,
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => {
      loaded.current = true;
      apply(instance, latest.current, fitted);
    });
    instance.on("click", "network", (event: maplibregl.MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.segment_id;
      if (typeof id === "string") {
        latest.current.select?.(id);
      }
    });
    instance.on("mouseenter", "network", () => {
      instance.getCanvas().style.cursor = "pointer";
    });
    instance.on("mouseleave", "network", () => {
      instance.getCanvas().style.cursor = "";
    });
    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
      loaded.current = false;
      fitted.current = false;
    };
  }, []);

  useEffect(() => {
    if (map.current && loaded.current) {
      apply(map.current, latest.current, fitted);
    }
  }, [network, points, routes, highlight]);

  return (
    <div
      ref={container}
      className="map"
      role="region"
      aria-label={label}
      data-features={(network?.features.length ?? 0) + points.length}
    />
  );
}

function apply(instance: maplibregl.Map, data: Latest, fitted: { current: boolean }) {
  (instance.getSource("network") as maplibregl.GeoJSONSource | undefined)?.setData(
    data.network ?? EMPTY,
  );
  (instance.getSource("routes") as maplibregl.GeoJSONSource | undefined)?.setData(
    data.routes ?? EMPTY,
  );
  (instance.getSource("points") as maplibregl.GeoJSONSource | undefined)?.setData(
    toGeoJson(data.points),
  );
  instance.setFilter("network-highlight", ["==", ["get", "segment_id"], data.highlight ?? ""]);
  if (!fitted.current && fit(instance, data)) {
    fitted.current = true;
  }
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

function fit(instance: maplibregl.Map, data: Latest): boolean {
  const bounds = new maplibregl.LngLatBounds();
  let any = false;
  const extend = (lon: number, lat: number) => {
    bounds.extend([lon, lat]);
    any = true;
  };
  for (const f of data.routes?.features ?? []) {
    if (f.geometry.type === "LineString") {
      for (const c of f.geometry.coordinates) extend(c[0]!, c[1]!);
    }
  }
  if (!any) {
    for (const p of data.points) extend(p.lon, p.lat);
  }
  if (!any) {
    for (const f of data.network?.features ?? []) {
      if (f.geometry.type === "LineString") {
        for (const c of f.geometry.coordinates) extend(c[0]!, c[1]!);
      }
    }
  }
  if (any) {
    instance.fitBounds(bounds, { padding: 30, animate: false, maxZoom: 12 });
  }
  return any;
}
