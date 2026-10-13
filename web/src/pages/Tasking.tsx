import { useQuery } from "@tanstack/react-query";
import type { FeatureCollection } from "geojson";
import { Suspense, lazy, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { MODE, getJson } from "../api/client";
import type { MethodInfo, Summary } from "../api/types";
import { Abbr } from "../components/Abbr";
import { IntervalChart } from "../components/IntervalChart";
import { ErrorState, Loading, Partial } from "../components/States";
import { formatNumber } from "../lib/format";
import { useSettings } from "../lib/settings";

const MapView = lazy(() => import("../components/MapView"));
const LIVE_BASE = (import.meta.env.VITE_SIKKA_API as string | undefined) ?? "http://127.0.0.1:8000";

interface MissionInfo {
  mission_id: string;
  segments: string[];
  waypoints: [number, number, number][];
  path_km: number;
  flight_s: number;
  value: number;
  feasible: boolean;
  reason: string;
  plan_valid: boolean;
}

interface TaskingData {
  disclaimer: string;
  profile: {
    endurance_min: number;
    speed_mps: number;
    reserve_share: number;
    altitude_m: number;
    usable_s: number;
  };
  budget_missions: number;
  missions: MissionInfo[];
  refused: MissionInfo[];
  value_of_information: { segment_id: string; voi: number; length_km: number }[];
  comparison: Record<
    string,
    { segments: string[]; value: number; flight_s: number; missions: number }
  >;
}

function download(path: string): string {
  return MODE === "static"
    ? `${import.meta.env.BASE_URL}snapshot/downloads/${path}`
    : `${LIVE_BASE}/v1/tasking/${path.endsWith(".plan") ? `plan/${path.replace(".plan", "")}` : `export/${path.split(".").pop()}`}`;
}

export function Tasking() {
  const { t } = useTranslation();
  const settings = useSettings();
  const data = useQuery({
    queryKey: ["tasking"],
    queryFn: () => getJson<TaskingData>("/v1/tasking/missions"),
  });
  const network = useQuery({
    queryKey: ["network"],
    queryFn: () => getJson<FeatureCollection>("/v1/network"),
  });
  const method = useQuery({
    queryKey: ["method"],
    queryFn: () => getJson<MethodInfo>("/v1/method"),
  });
  const routes = useMemo<FeatureCollection | null>(
    () =>
      data.data
        ? {
            type: "FeatureCollection",
            features: data.data.missions.map((m) => ({
              type: "Feature",
              properties: { mission_id: m.mission_id },
              geometry: { type: "LineString", coordinates: m.waypoints.map((w) => [w[0], w[1]]) },
            })),
          }
        : null,
    [data.data],
  );
  const e5 = method.data?.results.e5_tasking;
  const n = (v: number, d = 0) => formatNumber(v, settings, d);

  return (
    <section aria-labelledby="tasking-title">
      <h1 id="tasking-title">{t("tasking.title")}</h1>
      <p>
        {t("tasking.intro_1")} <Abbr term="VOI" /> {t("tasking.intro_2")}
      </p>
      <p className="state" role="note" data-testid="tasking-disclaimer">
        {t("tasking.disclaimer")}
      </p>
      {data.isPending ? <Loading /> : null}
      {data.isError ? <ErrorState error={data.error} /> : null}
      {data.data ? (
        <>
          <div className="grid two">
            <div className="card">
              <h2>{t("tasking.missions")}</h2>
              <p className="muted">
                {t("tasking.profile", {
                  endurance: n(data.data.profile.endurance_min),
                  speed: n(data.data.profile.speed_mps),
                  reserve: n(data.data.profile.reserve_share * 100),
                  altitude: n(data.data.profile.altitude_m),
                  usable: n(data.data.profile.usable_s),
                })}
              </p>
              <table data-testid="missions">
                <thead>
                  <tr>
                    <th scope="col">{t("tasking.mission")}</th>
                    <th scope="col">{t("tasking.segments")}</th>
                    <th scope="col">{t("tasking.path")}</th>
                    <th scope="col">{t("tasking.flight")}</th>
                    <th scope="col">{t("tasking.plan")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data.missions.map((m) => (
                    <tr key={m.mission_id}>
                      <th scope="row" className="mono">
                        {m.mission_id}
                      </th>
                      <td className="mono">{m.segments.join(", ")}</td>
                      <td className="num">{n(m.path_km, 1)} km</td>
                      <td>
                        <meter
                          min={0}
                          max={data.data.profile.usable_s}
                          value={m.flight_s}
                          aria-label={t("tasking.flight_meter", {
                            flight: n(m.flight_s),
                            usable: n(data.data.profile.usable_s),
                          })}
                        />{" "}
                        <span className="num">
                          {t("tasking.flight_of", {
                            flight: n(m.flight_s),
                            usable: n(data.data.profile.usable_s),
                          })}
                        </span>
                      </td>
                      <td>
                        <a href={download(`${m.mission_id}.plan`)} download>
                          {m.mission_id}.plan
                        </a>{" "}
                        <span className="muted">
                          {m.plan_valid ? t("tasking.plan_valid") : t("tasking.plan_invalid")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="row" style={{ marginBlockStart: 12 }}>
                <a className="button" href={download("sikka-missions.geojson")} download>
                  GeoJSON
                </a>
                <a className="button" href={download("sikka-missions.kml")} download>
                  KML
                </a>
              </p>
              {data.data.refused.length > 0 ? (
                <p className="muted">
                  {t("tasking.refused", {
                    segments: data.data.refused.flatMap((m) => m.segments).join(", "),
                  })}
                </p>
              ) : null}
            </div>
            <div className="card">
              <h2>{t("tasking.map")}</h2>
              <Suspense fallback={<Loading />}>
                <MapView
                  network={network.data ?? null}
                  points={[]}
                  routes={routes}
                  label={t("tasking.map")}
                />
              </Suspense>
            </div>
          </div>
          <div className="grid two">
            <div className="card">
              <h2>{t("tasking.voi")}</h2>
              <p className="muted">{t("tasking.voi_help")}</p>
              <div
                className="table-wrap"
                style={{ maxBlockSize: 360, overflowY: "auto" }}
                tabIndex={0}
                role="region"
                aria-label={t("tasking.voi")}
              >
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{t("blackspots.segment")}</th>
                      <th scope="col">
                        <Abbr term="VOI" />
                      </th>
                      <th scope="col">{t("tasking.length")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.data.value_of_information.slice(0, 30).map((v) => (
                      <tr key={v.segment_id}>
                        <td className="mono">{v.segment_id}</td>
                        <td className="num">{n(v.voi, 3)}</td>
                        <td className="num">{n(v.length_km, 1)} km</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="card">
              <h2>{t("tasking.comparison")}</h2>
              <p className="muted">{t("tasking.comparison_help")}</p>
              <table data-testid="tasking-comparison">
                <thead>
                  <tr>
                    <th scope="col">{t("tasking.strategy")}</th>
                    <th scope="col">{t("tasking.value")}</th>
                    <th scope="col">{t("tasking.segments")}</th>
                    <th scope="col">{t("tasking.flight")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.data.comparison).map(([name, c]) => (
                    <tr key={name}>
                      <th scope="row">{t(`tasking.s_${name}`)}</th>
                      <td className="num">{n(c.value, 3)}</td>
                      <td className="num">{n(c.segments.length)}</td>
                      <td className="num">{n(c.flight_s)} s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h3 style={{ marginBlockStart: 16 }}>{t("tasking.e5")}</h3>
              {e5 ? (
                <IntervalChart
                  title={t("tasking.strategy")}
                  valueLabel={t("tasking.reduction")}
                  ariaLabel={t("tasking.e5_chart")}
                  domain={[-0.1, 0.1]}
                  items={e5.strategies.map((s) => {
                    const v: Summary | undefined = e5.summary[`${s}_reduction`];
                    return {
                      label: t(`tasking.s_${s}`),
                      estimate: v?.estimate ?? 0,
                      low: v?.low ?? 0,
                      high: v?.high ?? 0,
                    };
                  })}
                />
              ) : (
                <Partial>{t("method.no_results")}</Partial>
              )}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
