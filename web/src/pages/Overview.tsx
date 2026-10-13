import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getJson } from "../api/client";
import type { Conformance } from "../api/types";
import { IntervalChart } from "../components/IntervalChart";
import { ErrorState, Loading, Partial } from "../components/States";
import { formatInterval, formatNumber, formatPercent } from "../lib/format";
import { useSettings } from "../lib/settings";

const FAMILIES = ["S", "V", "R", "X", "T", "P", "ALL"];

export function Overview() {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ["conformance"],
    queryFn: () => getJson<Conformance>("/v1/producers/conformance"),
  });

  return (
    <section aria-labelledby="overview-title">
      <h1 id="overview-title">{t("overview.title")}</h1>
      <p>{t("overview.intro")}</p>
      {query.isPending ? <Loading /> : null}
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data ? <OverviewBody data={query.data} /> : null}
      <div className="card">
        <h2>{t("overview.top10")}</h2>
        <Partial>{t("state.pending_layer")}</Partial>
      </div>
    </section>
  );
}

function OverviewBody({ data }: { data: Conformance }) {
  const { t } = useTranslation();
  const settings = useSettings();
  const h = data.headline;
  const producers = [...new Set(data.scores.map((s) => s.producer_id))].sort();
  const overall = data.scores
    .filter((s) => s.family === "ALL")
    .map((s) => ({ label: s.producer_id, estimate: s.estimate, low: s.low, high: s.high }));
  return (
    <>
      <p className="muted">
        {t("overview.dataset")}: {t(`overview.dataset_${data.dataset}`)}
      </p>
      <div className="grid four" style={{ marginBlockEnd: 24 }}>
        <div className="card figure" data-testid="figure-producers">
          <span>{t("overview.producers_conforming")}</span>
          <span className="value">
            {formatNumber(h.producers_conforming, settings)} / {formatNumber(h.producers, settings)}
          </span>
          <span className="interval">
            {t("overview.producers_range", {
              low: formatNumber(h.producers_conforming_low, settings),
              high: formatNumber(h.producers_conforming_high, settings),
              total: formatNumber(h.producers, settings),
            })}
          </span>
          <span className="muted">
            {t("overview.producers_conforming_help", {
              threshold: formatNumber(h.conforming_threshold * 100, settings),
            })}
          </span>
        </div>
        <div className="card figure" data-testid="figure-rules">
          <span>{t("overview.rules_failing")}</span>
          <span className="value">
            {formatNumber(h.rules_failing, settings)} / {formatNumber(h.rules_total, settings)}
          </span>
          <span className="interval">{t("common.exact_count")}</span>
          <span className="muted">{t("overview.rules_failing_help")}</span>
        </div>
        <div className="card figure" data-testid="figure-ranked">
          <span>{t("overview.segments_ranked")}</span>
          <Partial>{t("state.pending_layer")}</Partial>
        </div>
        <div className="card figure" data-testid="figure-abstained">
          <span>{t("overview.segments_abstained")}</span>
          <Partial>{t("state.pending_layer")}</Partial>
        </div>
      </div>
      <div className="card">
        <h2>{t("overview.matrix")}</h2>
        <p className="muted">{t("overview.matrix_help")}</p>
        <IntervalChart
          items={overall}
          title={t("family.ALL")}
          ariaLabel={t("overview.chart_aria")}
        />
        <div className="table-wrap" style={{ marginBlockStart: 16 }}>
          <table data-testid="conformance-matrix">
            <caption className="visually-hidden">{t("overview.matrix")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("common.producer")}</th>
                {FAMILIES.map((f) => (
                  <th scope="col" key={f}>
                    {t(`family.${f}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {producers.map((p) => (
                <tr key={p}>
                  <th scope="row" className="mono">
                    {p}
                  </th>
                  {FAMILIES.map((f) => {
                    const s = data.scores.find((x) => x.producer_id === p && x.family === f);
                    return (
                      <td key={f} className="num">
                        {s ? (
                          <>
                            {formatPercent(s.estimate, settings)}
                            <br />
                            <span className="muted">{formatInterval(s.low, s.high, settings)}</span>
                          </>
                        ) : (
                          "-"
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">{t("overview.score_definition")}</p>
      </div>
    </>
  );
}
