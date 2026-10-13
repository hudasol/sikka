import { useMutation, useQuery } from "@tanstack/react-query";
import type { FeatureCollection } from "geojson";
import { Suspense, lazy, useMemo, useState } from "react";
import type { DragEvent } from "react";
import { useTranslation } from "react-i18next";

import {
  MODE,
  StaticModeError,
  getJson,
  reportHtmlUrl,
  reportJsonUrl,
  validateSample,
  validateUpload,
} from "../api/client";
import type { Report, RuleResult, Sample } from "../api/types";
import { SeverityBadge } from "../components/SeverityBadge";
import { Empty, ErrorState, Loading } from "../components/States";
import { formatNumber, formatPercent } from "../lib/format";
import { useSettings } from "../lib/settings";

const MapView = lazy(() => import("../components/MapView"));
const FAMILIES = ["S", "V", "R", "X", "T", "P"] as const;

export function Validate() {
  const { t } = useTranslation();
  const samples = useQuery({
    queryKey: ["samples"],
    queryFn: () => getJson<Sample[]>("/v1/samples"),
  });
  const [chosen, setChosen] = useState<string>("broken/crash_records_producer_b.ndjson");
  const [dragging, setDragging] = useState(false);
  const run = useMutation({
    mutationFn: async (input: { sample?: Sample; file?: File }) => {
      const response = input.file
        ? await validateUpload(input.file)
        : await validateSample(input.sample!);
      return getJson<Report>(`/v1/reports/${response.report_id}`);
    },
  });

  const sample = samples.data?.find((s) => s.name === chosen);
  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file && MODE === "live") {
      run.mutate({ file });
    }
  };

  return (
    <section aria-labelledby="validate-title">
      <h1 id="validate-title">{t("validate.title")}</h1>
      <p>{t("validate.intro")}</p>
      <div className="grid two">
        <div className="card">
          <label htmlFor="sample-select">
            <strong>{t("validate.sample")}</strong>
          </label>
          {samples.isPending ? <Loading /> : null}
          {samples.isError ? <ErrorState error={samples.error} /> : null}
          {samples.data ? (
            <div className="row" style={{ marginBlockStart: 8 }}>
              <select id="sample-select" value={chosen} onChange={(e) => setChosen(e.target.value)}>
                {samples.data.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.file} ({t(`validate.sample_${s.set}`)})
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="primary"
                disabled={!sample || run.isPending}
                onClick={() => sample && run.mutate({ sample })}
              >
                {t("validate.run")}
              </button>
            </div>
          ) : null}
        </div>
        <div
          className={`dropzone${dragging ? " active" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(MODE === "live");
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          {MODE === "live" ? (
            <>
              <p>{t("validate.drop")}</p>
              <label className="button" htmlFor="file-input">
                {t("validate.choose")}
              </label>
              <input
                id="file-input"
                type="file"
                accept=".ndjson,.jsonl,.csv,.geojson,.json"
                className="visually-hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    run.mutate({ file });
                  }
                }}
              />
            </>
          ) : (
            <p data-testid="upload-disabled">{t("validate.upload_disabled")}</p>
          )}
        </div>
      </div>
      {run.isPending ? <Loading label={t("validate.running")} /> : null}
      {run.isError ? (
        <ErrorState
          error={
            run.error instanceof StaticModeError
              ? new Error(t("validate.upload_disabled"))
              : new Error(t("validate.failed", { detail: run.error.message }))
          }
        />
      ) : null}
      {run.data ? <ReportView report={run.data} /> : null}
    </section>
  );
}

function ReportView({ report }: { report: Report }) {
  const { t } = useTranslation();
  const settings = useSettings();
  const network = useQuery({
    queryKey: ["network"],
    queryFn: () => getJson<FeatureCollection>("/v1/network"),
  });
  const points = useMemo(() => {
    const seen = new Map<number, { id: string; lat: number; lon: number; kind: string }>();
    for (const rule of report.rules) {
      for (const [row, lat, lon] of rule.locations) {
        if (!seen.has(row)) {
          seen.set(row, { id: `${row}`, lat, lon, kind: rule.rule_id });
        }
      }
    }
    return [...seen.values()];
  }, [report]);

  return (
    <div className="card" aria-live="polite" data-testid="report">
      <h2>{t("validate.results")}</h2>
      <p className="mono">{t("validate.results_for", { id: report.report_id })}</p>
      <div className="row">
        <a className="button" href={reportJsonUrl(report.report_id)} download>
          {t("common.download_json")}
        </a>
        <a
          className="button"
          href={reportHtmlUrl(report.report_id)}
          target="_blank"
          rel="noreferrer"
        >
          {t("common.download_html")}
        </a>
      </div>
      <h3 style={{ marginBlockStart: 20 }}>{t("validate.files")}</h3>
      <ul>
        {report.files.map((f) => (
          <li key={f.file}>
            <span className="mono">{f.file}</span>:{" "}
            {t("validate.file_summary", {
              rows: formatNumber(f.rows, settings),
              quarantined: formatNumber(f.quarantined_rows, settings),
            })}
          </li>
        ))}
      </ul>
      <h3>{t("validate.by_family")}</h3>
      {FAMILIES.map((family) => {
        const rules = report.rules.filter((r) => r.family === family);
        const failing = rules.filter((r) => r.findings > 0);
        return (
          <details key={family} open={failing.length > 0 && family !== "X"}>
            <summary>
              {t(`family.${family}`)} ({family}):{" "}
              {t("validate.rules_with_findings", { count: failing.length })}
            </summary>
            <div className="details-body">
              {failing.length === 0 ? <Empty>{t("validate.no_findings")}</Empty> : null}
              {failing.map((rule) => (
                <RuleItem key={`${rule.rule_id}-${rule.file}`} rule={rule} />
              ))}
              {rules
                .filter((r) => r.status === "skipped")
                .map((r) => (
                  <p key={r.rule_id} className="muted">
                    <span className="mono">{r.rule_id}</span>: {t("common.not_evaluated")} ({r.note}
                    )
                  </p>
                ))}
            </div>
          </details>
        );
      })}
      <h3 style={{ marginBlockStart: 20 }}>{t("validate.map")}</h3>
      <p className="muted">{t("validate.map_help")}</p>
      {points.length > 0 ? (
        <>
          <Suspense fallback={<Loading />}>
            <MapView network={network.data ?? null} points={points} label={t("validate.map")} />
          </Suspense>
          <details>
            <summary>{t("validate.map_table")}</summary>
            <div className="details-body table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t("common.row")}</th>
                    <th scope="col">{t("common.rule")}</th>
                    <th scope="col">lat</th>
                    <th scope="col">lon</th>
                  </tr>
                </thead>
                <tbody>
                  {points.slice(0, 200).map((p) => (
                    <tr key={p.id}>
                      <td className="num">{p.id}</td>
                      <td className="mono">{p.kind}</td>
                      <td className="num">{formatNumber(p.lat, settings, 5)}</td>
                      <td className="num">{formatNumber(p.lon, settings, 5)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : (
        <Empty />
      )}
    </div>
  );
}

function RuleItem({ rule }: { rule: RuleResult }) {
  const { t } = useTranslation();
  const settings = useSettings();
  return (
    <details>
      <summary>
        <span className="mono">{rule.rule_id}</span> {rule.title}{" "}
        <SeverityBadge severity={rule.severity} />{" "}
        <span className="num">
          {formatNumber(rule.records || rule.findings, settings)} (
          {formatPercent(rule.share, settings, 2)})
        </span>
      </summary>
      <div className="details-body">
        <p>
          <strong>{t("common.file")}:</strong> <span className="mono">{rule.file}</span>
        </p>
        {rule.fields.length > 0 ? (
          <p>
            <strong>{t("common.fields")}:</strong>{" "}
            <span className="mono">{rule.fields.join(", ")}</span>
          </p>
        ) : null}
        <p>
          <strong>{t("common.examples")}:</strong>
        </p>
        <ul>
          {rule.examples.map((e, i) => (
            <li key={i}>
              <span className="mono">{e.record_id ?? `${t("common.row")} ${e.row ?? ""}`}</span>:{" "}
              {e.detail}
            </li>
          ))}
        </ul>
        <p>
          <strong>{t("common.fix")}:</strong> {rule.fix_hint}
        </p>
      </div>
    </details>
  );
}
