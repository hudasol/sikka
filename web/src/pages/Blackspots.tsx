import { useQuery } from "@tanstack/react-query";
import type { FeatureCollection } from "geojson";
import { Suspense, lazy, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { getJson } from "../api/client";
import type { Ranking, SegmentDetail, SegmentRow } from "../api/types";
import { Abbr } from "../components/Abbr";
import { Drawer } from "../components/Drawer";
import { RankWhisker } from "../components/RankWhisker";
import { Empty, ErrorState, Loading } from "../components/States";
import { formatNumber, formatPercent, formatYear } from "../lib/format";
import { useSettings } from "../lib/settings";

const MapView = lazy(() => import("../components/MapView"));

type SortKey = "rank" | "p_top_k" | "psi_per_year" | "observed" | "raw_rank" | "rate_rank";
type Quality = "all" | "unresolved" | "corrected";

export function Blackspots() {
  const { t } = useTranslation();
  const settings = useSettings();
  const [dataset, setDataset] = useState<"broken" | "clean">("broken");
  const [corridor, setCorridor] = useState("all");
  const [quality, setQuality] = useState<Quality>("all");
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({ key: "rank", asc: true });
  const [selected, setSelected] = useState<string | null>(null);
  const ranking = useQuery({
    queryKey: ["ranking", dataset],
    queryFn: () =>
      getJson<Ranking>(
        dataset === "clean" ? "/v1/segments/ranking?dataset=clean" : "/v1/segments/ranking",
      ),
  });
  const network = useQuery({
    queryKey: ["network"],
    queryFn: () => getJson<FeatureCollection>("/v1/network"),
  });

  const rows = useMemo(() => {
    const all = ranking.data?.segments ?? [];
    const ranked = all.filter((s) => !s.abstained);
    const filtered = ranked.filter((s) => {
      if (corridor !== "all" && s.corridor !== corridor) return false;
      if (quality === "unresolved" && s.unresolved_pairs === 0) return false;
      if (quality === "corrected" && (s.quality_factor ?? 1) <= 1.0001) return false;
      return true;
    });
    const value = (s: SegmentRow) => (s[sort.key] ?? Number.POSITIVE_INFINITY) as number;
    return [...filtered].sort((a, b) => (sort.asc ? value(a) - value(b) : value(b) - value(a)));
  }, [ranking.data, corridor, quality, sort]);

  const corridors = useMemo(
    () => [...new Set((ranking.data?.segments ?? []).map((s) => s.corridor))].sort(),
    [ranking.data],
  );
  const abstained = (ranking.data?.segments ?? []).filter((s) => s.abstained);
  const max = (ranking.data?.segments ?? []).filter((s) => !s.abstained).length || 1;
  const topK = ranking.data?.summary.published.top_k ?? 12;

  const header = (key: SortKey, label: string) => {
    const active = sort.key === key;
    return (
      <th scope="col" aria-sort={active ? (sort.asc ? "ascending" : "descending") : "none"}>
        <button
          type="button"
          className="link-button"
          onClick={() =>
            setSort({
              key,
              asc: active
                ? !sort.asc
                : key !== "p_top_k" && key !== "psi_per_year" && key !== "observed",
            })
          }
        >
          {label}
          {active ? (sort.asc ? " ▲" : " ▼") : ""}
        </button>
      </th>
    );
  };

  return (
    <section aria-labelledby="blackspots-title">
      <h1 id="blackspots-title">{t("blackspots.title")}</h1>
      <p>
        {t("blackspots.intro_1")} (<Abbr term="PSI" />
        ), {t("blackspots.intro_2")} (
        <Abbr term="EB" />
        ), {t("blackspots.intro_3")}
      </p>
      <fieldset className="card soft">
        <legend>{t("blackspots.controls")}</legend>
        <div className="row">
          <span role="radiogroup" aria-label={t("blackspots.dataset")} className="row">
            {(["broken", "clean"] as const).map((d) => (
              <label key={d}>
                <input
                  type="radio"
                  name="dataset"
                  value={d}
                  checked={dataset === d}
                  onChange={() => setDataset(d)}
                />{" "}
                {t(`blackspots.dataset_${d}`)}
              </label>
            ))}
          </span>
          <label>
            {t("blackspots.corridor")}{" "}
            <select value={corridor} onChange={(e) => setCorridor(e.target.value)}>
              <option value="all">{t("blackspots.all")}</option>
              {corridors.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("blackspots.quality")}{" "}
            <select value={quality} onChange={(e) => setQuality(e.target.value as Quality)}>
              <option value="all">{t("blackspots.all")}</option>
              <option value="unresolved">{t("blackspots.quality_unresolved")}</option>
              <option value="corrected">{t("blackspots.quality_corrected")}</option>
            </select>
          </label>
        </div>
        <p className="muted">{t(`blackspots.dataset_${dataset}_help`)}</p>
      </fieldset>
      {ranking.isPending ? <Loading /> : null}
      {ranking.isError ? (
        <ErrorState error={ranking.error} onRetry={() => void ranking.refetch()} />
      ) : null}
      {ranking.data ? (
        <>
          <div className="grid">
            <div className="card">
              <h2>{t("blackspots.table")}</h2>
              <p className="muted">
                {t("blackspots.table_help", {
                  k: formatNumber(topK, settings),
                  draws: formatNumber(ranking.data.summary.published.draws, settings),
                })}
              </p>
              {rows.length === 0 ? <Empty /> : null}
              <div
                className="table-wrap"
                style={{ maxBlockSize: 560, overflowY: "auto" }}
                tabIndex={0}
                role="region"
                aria-label={t("blackspots.table")}
              >
                <table data-testid="ranking-table">
                  <caption className="visually-hidden">{t("blackspots.table")}</caption>
                  <thead>
                    <tr>
                      {header("rank", t("blackspots.rank"))}
                      <th scope="col">{t("blackspots.interval")}</th>
                      {header("p_top_k", t("blackspots.p_top", { k: topK }))}
                      <th scope="col">{t("blackspots.segment")}</th>
                      {header("psi_per_year", t("blackspots.psi"))}
                      {header("observed", t("blackspots.observed"))}
                      {header("raw_rank", t("blackspots.raw_rank"))}
                      {header("rate_rank", t("blackspots.rate_rank"))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => (
                      <tr
                        key={s.segment_id}
                        aria-selected={selected === s.segment_id}
                        className={selected === s.segment_id ? "selected" : undefined}
                      >
                        <td className="num">{formatNumber(s.rank ?? 0, settings)}</td>
                        <td>
                          <RankWhisker
                            rank={s.rank ?? 0}
                            low={s.rank_low ?? 0}
                            high={s.rank_high ?? 0}
                            max={max}
                          />
                        </td>
                        <td className="num">{formatPercent(s.p_top_k ?? 0, settings, 0)}</td>
                        <td>
                          <button
                            type="button"
                            className="link-button mono"
                            onClick={() => setSelected(s.segment_id)}
                          >
                            {s.segment_id}
                          </button>
                          <br />
                          <span className="muted">
                            {settings.lang === "ar" ? s.road_name_ar : s.road_name_en}
                          </span>
                        </td>
                        <td className="num">{formatNumber(s.psi_per_year ?? 0, settings, 2)}</td>
                        <td className="num">{formatNumber(s.observed, settings)}</td>
                        <td className="num">{formatNumber(s.raw_rank ?? 0, settings)}</td>
                        <td className="num">
                          {s.rate_rank ? formatNumber(s.rate_rank, settings) : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="card">
              <h2>{t("blackspots.map")}</h2>
              <p className="muted">{t("blackspots.map_help")}</p>
              <Suspense fallback={<Loading />}>
                <MapView
                  network={network.data ?? null}
                  points={[]}
                  label={t("blackspots.map")}
                  highlight={selected}
                  onSelectSegment={setSelected}
                />
              </Suspense>
            </div>
          </div>
          <div className="card">
            <h2>{t("blackspots.abstained", { count: abstained.length })}</h2>
            <p className="muted">{t("blackspots.abstained_help")}</p>
            <details>
              <summary>{t("blackspots.abstained_list")}</summary>
              <div className="details-body table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{t("blackspots.segment")}</th>
                      <th scope="col">{t("blackspots.reason")}</th>
                      <th scope="col">{t("blackspots.observed")}</th>
                      <th scope="col">{t("blackspots.raw_rank")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {abstained.map((s) => (
                      <tr key={s.segment_id}>
                        <td className="mono">{s.segment_id}</td>
                        <td>
                          {(s.abstained ?? "")
                            .split(";")
                            .map((r) => t(`reason.${r}`))
                            .join("; ")}
                        </td>
                        <td className="num">{formatNumber(s.observed, settings)}</td>
                        <td className="num">{formatNumber(s.raw_rank ?? 0, settings)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
          <ModelPanel ranking={ranking.data} />
        </>
      ) : null}
      {selected ? (
        <SegmentDrawer id={selected} dataset={dataset} onClose={() => setSelected(null)} />
      ) : null}
    </section>
  );
}

function ModelPanel({ ranking }: { ranking: Ranking }) {
  const { t } = useTranslation();
  const settings = useSettings();
  const spf = ranking.summary.spf;
  return (
    <div className="grid two">
      <div className="card">
        <h2>
          <Abbr term="SPF" /> {t("blackspots.spf")}
        </h2>
        {spf ? (
          <>
            <table>
              <thead>
                <tr>
                  <th scope="col">{t("blackspots.term")}</th>
                  <th scope="col">{t("blackspots.estimate")}</th>
                  <th scope="col">{t("blackspots.std_error")}</th>
                </tr>
              </thead>
              <tbody>
                {spf.coefficients.map((c) => (
                  <tr key={c.name}>
                    <th scope="row" className="mono">
                      {c.name}
                    </th>
                    <td className="num">{formatNumber(c.estimate, settings, 3)}</td>
                    <td className="num">{formatNumber(c.std_error, settings, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted">
              {t("blackspots.spf_fit", {
                k: formatNumber(spf.k, settings, 2),
                n: formatNumber(spf.n_segments, settings),
                r2: formatNumber(spf.pseudo_r2_mcfadden, settings, 3),
                pearson: formatNumber(spf.pearson_dispersion, settings, 2),
              })}
            </p>
          </>
        ) : (
          <Empty />
        )}
      </div>
      <div className="card">
        <h2>{t("blackspots.capture")}</h2>
        <p className="muted">{t("blackspots.capture_help")}</p>
        <table>
          <thead>
            <tr>
              <th scope="col">{t("blackspots.group")}</th>
              <th scope="col">{t("blackspots.seen")}</th>
              <th scope="col">{t("blackspots.estimated_total")}</th>
              <th scope="col">{t("blackspots.completeness")}</th>
            </tr>
          </thead>
          <tbody>
            {ranking.summary.capture_recapture.map((c) => (
              <tr key={c.group}>
                <th scope="row" className="mono">
                  {c.group}
                </th>
                <td className="num">{formatNumber(c.seen_by_either, settings)}</td>
                <td className="num">
                  {formatNumber(c.estimated_total, settings)}{" "}
                  <span className="muted">
                    ({formatNumber(c.estimated_total_low, settings)} {t("common.to")}{" "}
                    {formatNumber(c.estimated_total_high, settings)})
                  </span>
                </td>
                <td className="num">{formatPercent(c.completeness, settings)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SegmentDrawer({
  id,
  dataset,
  onClose,
}: {
  id: string;
  dataset: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const settings = useSettings();
  const detail = useQuery({
    queryKey: ["segment", id, dataset],
    queryFn: () => getJson<SegmentDetail>(`/v1/segments/${id}`),
  });
  const n = (v: number | null | undefined, d = 2) =>
    v === null || v === undefined ? "-" : formatNumber(v, settings, d);
  return (
    <Drawer title={id} onClose={onClose}>
      {detail.isPending ? <Loading /> : null}
      {detail.isError ? <ErrorState error={detail.error} /> : null}
      {detail.data ? (
        <div data-testid="segment-drawer">
          <p>
            {settings.lang === "ar" ? detail.data.road_name_ar : detail.data.road_name_en} ·{" "}
            {t(`road_class.${detail.data.road_class}`)} · {n(detail.data.length_km, 1)} km
          </p>
          <h3>{t("blackspots.why")}</h3>
          {detail.data.explanation.kind === "abstained" ? (
            <p>
              {t("blackspots.why_abstained", {
                reasons: (detail.data.explanation.reasons ?? [])
                  .map((r) => t(`reason.${r}`))
                  .join("; "),
              })}
            </p>
          ) : (
            <p data-testid="why">
              {t("blackspots.why_ranked", {
                observed: n(detail.data.explanation.observed_per_year),
                predicted: n(detail.data.explanation.predicted_per_year),
                ratio: n(detail.data.explanation.ratio ?? null, 1),
                weight: formatPercent(detail.data.explanation.eb_weight ?? 0, settings, 0),
                eb: n(detail.data.explanation.eb_per_year ?? null),
                psi: n(detail.data.explanation.psi_per_year ?? null),
                rank: n(detail.data.explanation.rank ?? null, 0),
                low: n(detail.data.explanation.rank_low ?? null, 0),
                high: n(detail.data.explanation.rank_high ?? null, 0),
                p: formatPercent(detail.data.explanation.p_top_k ?? 0, settings, 0),
              })}
            </p>
          )}
          <table>
            <tbody>
              <tr>
                <th scope="row">
                  <Abbr term="SPF" /> {t("blackspots.predicted")}
                </th>
                <td className="num">{n(detail.data.predicted_per_year)}</td>
              </tr>
              <tr>
                <th scope="row">{t("blackspots.observed_per_year")}</th>
                <td className="num">
                  {n(detail.data.observed / Math.max(1e-9, detail.data.window_years))}
                </td>
              </tr>
              <tr>
                <th scope="row">
                  <Abbr term="EB" /> {t("blackspots.estimate")}
                </th>
                <td className="num">{n(detail.data.eb_per_year)}</td>
              </tr>
              <tr>
                <th scope="row">
                  <Abbr term="PSI" />
                </th>
                <td className="num">{n(detail.data.psi_per_year)}</td>
              </tr>
              <tr>
                <th scope="row">
                  <Abbr term="AADT" />
                </th>
                <td className="num">{n(detail.data.aadt, 0)}</td>
              </tr>
            </tbody>
          </table>
          <h3>{t("blackspots.caveats")}</h3>
          <ul>
            <li>
              {t("blackspots.caveat_quality", {
                factor: n(detail.data.quality_factor, 3),
              })}
            </li>
            <li>
              {t("blackspots.caveat_unresolved", {
                count: detail.data.unresolved_pairs,
              })}
            </li>
            <li>
              {t("blackspots.caveat_coverage", {
                coverage: formatPercent(detail.data.coverage, settings, 0),
              })}
            </li>
            <li>{t("blackspots.caveat_synthetic")}</li>
          </ul>
          {detail.data.clean_comparison ? (
            <>
              <h3>{t("blackspots.compare")}</h3>
              <p>
                {t("blackspots.compare_text", {
                  received: n(detail.data.rank, 0),
                  clean: n(detail.data.clean_comparison.rank, 0),
                })}
              </p>
            </>
          ) : null}
          <h3>{t("blackspots.by_year")}</h3>
          <table>
            <thead>
              <tr>
                {Object.keys(detail.data.observed_by_year).map((y) => (
                  <th scope="col" key={y}>
                    {formatYear(y, settings)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {Object.entries(detail.data.observed_by_year).map(([y, v]) => (
                  <td className="num" key={y}>
                    {formatNumber(v, settings)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}
    </Drawer>
  );
}
