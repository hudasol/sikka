import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getJson } from "../api/client";
import type { MethodInfo, Summary } from "../api/types";
import { Abbr } from "../components/Abbr";
import { IntervalChart } from "../components/IntervalChart";
import { ErrorState, Loading, Partial } from "../components/States";
import { formatNumber } from "../lib/format";
import { useSettings } from "../lib/settings";

const ASSUMPTIONS = ["synthetic", "spf_form", "exposure", "independence", "matching", "window"];
const LIMITS = ["synthetic", "author", "catalogue", "spf", "exposure", "capture", "tasking"];

function VerdictBadge({ verdict }: { verdict: string }) {
  const { t } = useTranslation();
  const shape = verdict === "HIT" ? "●" : verdict === "MISS" ? "×" : "○";
  const cls = verdict === "HIT" ? "ok" : verdict === "MISS" ? "error" : "info";
  return (
    <span className={`badge ${cls}`}>
      <span className="shape" aria-hidden="true">
        {shape}
      </span>
      {t(`method.verdict_${verdict}`)}
    </span>
  );
}

export function Method() {
  const { t } = useTranslation();
  const settings = useSettings();
  const data = useQuery({ queryKey: ["method"], queryFn: () => getJson<MethodInfo>("/v1/method") });
  const iv = (s: Summary | undefined, digits = 3) =>
    !s || s.estimate === null
      ? "-"
      : s.low === null || s.high === null || s.n < 2
        ? formatNumber(s.estimate, settings, digits)
        : `${formatNumber(s.estimate, settings, digits)} (${formatNumber(s.low, settings, digits)} ${t("common.to")} ${formatNumber(s.high, settings, digits)})`;

  return (
    <section aria-labelledby="method-title">
      <h1 id="method-title">{t("method.title")}</h1>
      <p>{t("method.intro")}</p>
      <div className="card">
        <h2>{t("method.assumptions")}</h2>
        <ul>
          {ASSUMPTIONS.map((a) => (
            <li key={a}>{t(`method.assumption_${a}`)}</li>
          ))}
        </ul>
        <p>
          <Abbr term="SPF" />, <Abbr term="EB" />, <Abbr term="PSI" />: {t("method.terms")}
        </p>
      </div>
      {data.isPending ? <Loading /> : null}
      {data.isError ? <ErrorState error={data.error} /> : null}
      {data.data ? (
        <>
          <div className="card">
            <h2>{t("method.predictions")}</h2>
            <p className="muted">{t("method.predictions_help")}</p>
            {data.data.results.predictions ? (
              <div className="table-wrap">
                <table data-testid="predictions">
                  <thead>
                    <tr>
                      <th scope="col">{t("method.id")}</th>
                      <th scope="col">{t("method.prediction")}</th>
                      <th scope="col">{t("method.observed")}</th>
                      <th scope="col">{t("method.verdict")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.data.results.predictions.predictions.map((p) => (
                      <tr key={p.id}>
                        <th scope="row" className="mono">
                          {p.id}
                        </th>
                        <td lang="en" dir="ltr">
                          {p.text}
                        </td>
                        <td lang="en" dir="ltr">
                          {p.observed}
                        </td>
                        <td>
                          <VerdictBadge verdict={p.verdict} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Partial>{t("method.no_results")}</Partial>
            )}
          </div>
          {data.data.results.e3_blackspot_ranking ? (
            <div className="card">
              <h2>{t("method.e3")}</h2>
              <IntervalChart
                title={t("method.method")}
                valueLabel={t("method.recall_rankable")}
                ariaLabel={t("method.e3_chart")}
                items={data.data.results.e3_blackspot_ranking.methods.flatMap((m) => {
                  const s = data.data.results.e3_blackspot_ranking!.summary[`${m}_recall_rankable`];
                  if (!s || s.estimate === null || s.low === null || s.high === null) {
                    return [];
                  }
                  return [
                    {
                      label: t(`method.m_${m}`),
                      estimate: s.estimate,
                      low: Math.max(0, s.low),
                      high: Math.min(1, s.high),
                    },
                  ];
                })}
              />
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t("method.method")}</th>
                    <th scope="col">{t("method.recall_all")}</th>
                    <th scope="col">{t("method.recall_rankable")}</th>
                    <th scope="col">{t("method.coverage")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data.results.e3_blackspot_ranking.methods.map((m) => {
                    const s = data.data.results.e3_blackspot_ranking!.summary;
                    return (
                      <tr key={m}>
                        <th scope="row">{t(`method.m_${m}`)}</th>
                        <td className="num">{iv(s[`${m}_recall_all`])}</td>
                        <td className="num">{iv(s[`${m}_recall_rankable`])}</td>
                        <td className="num">{iv(s[`${m}_coverage`])}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
          {data.data.results.e4_robustness ? (
            <div className="card">
              <h2>{t("method.e4")}</h2>
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t("method.scenario")}</th>
                    <th scope="col">{t("method.tau")}</th>
                    <th scope="col">{t("method.overlap")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.data.results.e4_robustness.summary).map(([s, v]) => (
                    <tr key={s}>
                      <th scope="row" className="mono">
                        {s}
                      </th>
                      <td className="num">{iv(v.eb?.kendall_tau)}</td>
                      <td className="num">{iv(v.eb?.top_k_overlap)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {data.data.results.e2_entity_resolution ? (
            <div className="card">
              <h2>{t("method.e2")}</h2>
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t("method.scenario")}</th>
                    <th scope="col">{t("method.precision")}</th>
                    <th scope="col">{t("method.recall")}</th>
                    <th scope="col">{t("method.abstention")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.data.results.e2_entity_resolution.summary).map(([s, v]) => (
                    <tr key={s}>
                      <th scope="row" className="mono">
                        {s}
                      </th>
                      <td className="num">{iv(v.precision)}</td>
                      <td className="num">{iv(v.recall)}</td>
                      <td className="num">{iv(v.abstention_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <div className="card">
            <h2>{t("method.ranking")}</h2>
            <p>
              {t("method.ranking_text", {
                ranked: formatNumber(data.data.ranking.published.ranked, settings),
                abstained: formatNumber(data.data.ranking.published.abstained, settings),
                draws: formatNumber(data.data.ranking.published.draws, settings),
              })}
            </p>
          </div>
        </>
      ) : null}
      <div className="card">
        <h2>{t("method.limits")}</h2>
        <ul data-testid="limitations">
          {LIMITS.map((l) => (
            <li key={l}>{t(`method.limit_${l}`)}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
