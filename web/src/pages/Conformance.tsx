import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { getJson } from "../api/client";
import type { Conformance as ConformanceData, FaultInfo } from "../api/types";
import { IntervalChart } from "../components/IntervalChart";
import { ErrorState, Loading } from "../components/States";
import { formatInterval, formatNumber, formatPercent } from "../lib/format";
import { useSettings } from "../lib/settings";

const FAMILIES = ["S", "V", "R", "X", "T", "P"];

export function Conformance() {
  const { t } = useTranslation();
  const settings = useSettings();
  const data = useQuery({
    queryKey: ["conformance"],
    queryFn: () => getJson<ConformanceData>("/v1/producers/conformance"),
  });
  const faults = useQuery({
    queryKey: ["faults"],
    queryFn: () => getJson<{ faults: FaultInfo[]; broken_rate: number }>("/v1/faults"),
  });
  const producers = [...new Set((data.data?.scores ?? []).map((s) => s.producer_id))].sort();

  return (
    <section aria-labelledby="conformance-title">
      <h1 id="conformance-title">{t("conformance.title")}</h1>
      <p>{t("conformance.intro")}</p>
      {data.isPending ? <Loading /> : null}
      {data.isError ? <ErrorState error={data.error} /> : null}
      {data.data
        ? producers.map((p) => {
            const scores = data.data.scores.filter((s) => s.producer_id === p);
            const overall = scores.find((s) => s.family === "ALL");
            const trend = data.data.trend.filter((x) => x.producer_id === p);
            return (
              <div className="card" key={p} data-testid={`scorecard-${p}`}>
                <h2 className="mono">{p}</h2>
                {overall ? (
                  <p>
                    {t("conformance.overall", {
                      share: formatPercent(overall.estimate, settings),
                      interval: formatInterval(overall.low, overall.high, settings),
                      passing: formatNumber(overall.passing, settings),
                      total: formatNumber(overall.total, settings),
                    })}
                  </p>
                ) : null}
                <div className="grid two">
                  <IntervalChart
                    title={t("common.family")}
                    ariaLabel={t("conformance.family_chart", { producer: p })}
                    items={FAMILIES.map((f) => scores.find((s) => s.family === f))
                      .filter((s): s is NonNullable<typeof s> => Boolean(s))
                      .map((s) => ({
                        label: `${t(`family.${s.family}`)} (${s.family})`,
                        estimate: s.estimate,
                        low: s.low,
                        high: s.high,
                      }))}
                  />
                  {trend.length > 0 ? (
                    <IntervalChart
                      title={t("conformance.period")}
                      ariaLabel={t("conformance.trend_chart", { producer: p })}
                      items={trend.map((x) => ({
                        label: x.period,
                        estimate: x.estimate,
                        low: x.low,
                        high: x.high,
                      }))}
                    />
                  ) : (
                    <p className="muted">{t("conformance.no_trend")}</p>
                  )}
                </div>
              </div>
            );
          })
        : null}
      <div className="card">
        <h2>{t("conformance.faults")}</h2>
        <p className="muted">
          {t("conformance.faults_help", {
            rate: formatPercent(faults.data?.broken_rate ?? 0, settings, 0),
          })}
        </p>
        {faults.isPending ? <Loading /> : null}
        {faults.data ? (
          <div className="table-wrap">
            <table data-testid="fault-catalogue">
              <thead>
                <tr>
                  <th scope="col">{t("conformance.fault")}</th>
                  <th scope="col">{t("conformance.description")}</th>
                  <th scope="col">{t("conformance.unit")}</th>
                  <th scope="col">{t("contract.rules")}</th>
                </tr>
              </thead>
              <tbody>
                {faults.data.faults.map((f) => (
                  <tr key={f.id}>
                    <th scope="row">
                      <span className="mono">{f.id}</span>{" "}
                      {settings.lang === "ar" ? (f.title_ar ?? f.title) : f.title}
                    </th>
                    <td lang="en" dir="ltr">
                      {f.description}
                    </td>
                    <td>{f.unit}</td>
                    <td className="mono">{f.expected_rules.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </section>
  );
}
