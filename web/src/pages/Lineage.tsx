import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { getLineage, searchLineage } from "../api/client";
import { Empty, ErrorState, Loading } from "../components/States";
import { useSettings } from "../lib/settings";
import { formatNumber } from "../lib/format";

function show(value: unknown): string {
  if (value === null || value === undefined) return "-";
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function Lineage() {
  const { t } = useTranslation();
  const settings = useSettings();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const results = useQuery({
    queryKey: ["lineage-search", submitted],
    queryFn: () => searchLineage(submitted),
  });
  const entry = useQuery({
    queryKey: ["lineage", selected],
    queryFn: () => getLineage(selected!),
    enabled: selected !== null,
  });

  return (
    <section aria-labelledby="lineage-title">
      <h1 id="lineage-title">{t("lineage.title")}</h1>
      <p>{t("lineage.intro")}</p>
      <form
        className="card soft row"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(query);
        }}
      >
        <label htmlFor="lineage-query">{t("lineage.search")}</label>
        <input
          id="lineage-query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="CC-..., PB-0000007, EX-SEG-DUN-001"
          className="mono"
          style={{ minInlineSize: 280, padding: 6, border: "2px solid var(--ink)" }}
        />
        <button type="submit" className="primary">
          {t("lineage.go")}
        </button>
      </form>
      <div className="grid two">
        <div className="card">
          <h2>{t("lineage.results")}</h2>
          {results.isPending ? <Loading /> : null}
          {results.isError ? <ErrorState error={results.error} /> : null}
          {results.data && results.data.length === 0 ? <Empty /> : null}
          <ul data-testid="lineage-results">
            {(results.data ?? []).map((item) => (
              <li key={item.canonical_id}>
                <button
                  type="button"
                  className="link-button mono"
                  aria-pressed={selected === item.canonical_id}
                  onClick={() => setSelected(item.canonical_id)}
                >
                  {item.canonical_id}
                </button>{" "}
                <span className="muted">
                  {t(`lineage.kind_${item.kind}`)} · {t(`lineage.status_${item.status}`)} ·{" "}
                  {item.record_ids.join(", ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="card" aria-live="polite">
          <h2>{t("lineage.chain")}</h2>
          {selected === null ? <Empty>{t("lineage.pick")}</Empty> : null}
          {entry.isPending && selected ? <Loading /> : null}
          {entry.isError ? <ErrorState error={entry.error} /> : null}
          {entry.data ? (
            <div data-testid="lineage-entry">
              <p>
                <span className="mono">{entry.data.canonical_id}</span> ·{" "}
                {t(`lineage.status_${entry.data.lineage.status}`)} · {entry.data.lineage.adapter}{" "}
                {entry.data.lineage.adapter_version}
              </p>
              <h3>{t("lineage.sources")}</h3>
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t("common.producer")}</th>
                    <th scope="col">{t("common.file")}</th>
                    <th scope="col">{t("common.row")}</th>
                    <th scope="col">{t("lineage.record_id")}</th>
                  </tr>
                </thead>
                <tbody>
                  {entry.data.lineage.sources.map((s) => (
                    <tr key={`${s.file}#${s.row}#${s.record_id}`}>
                      <td className="mono">{s.producer_id}</td>
                      <td className="mono">{s.file}</td>
                      <td className="num">{formatNumber(s.row, settings)}</td>
                      <td className="mono">{s.record_id ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h3>{t("lineage.transformations")}</h3>
              {entry.data.lineage.transformations.length === 0 ? (
                <p className="muted">{t("lineage.none")}</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{t("lineage.step")}</th>
                      <th scope="col">{t("contract.field")}</th>
                      <th scope="col">{t("lineage.before")}</th>
                      <th scope="col">{t("lineage.after")}</th>
                      <th scope="col">{t("lineage.note")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entry.data.lineage.transformations.map((tr, i) => (
                      <tr key={i}>
                        <td className="mono">{tr.step}</td>
                        <td className="mono">{tr.field}</td>
                        <td className="mono">{show(tr.before)}</td>
                        <td className="mono">{show(tr.after)}</td>
                        <td>{tr.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <h3>{t("lineage.findings")}</h3>
              {entry.data.lineage.findings.length === 0 ? (
                <p className="muted">{t("lineage.none")}</p>
              ) : (
                <ul>
                  {entry.data.lineage.findings.map((f, i) => (
                    <li key={i}>
                      <span className="mono">{f.rule_id}</span> {f.field ? `(${f.field})` : ""}{" "}
                      {f.detail ?? t("lineage.withheld")}
                    </li>
                  ))}
                </ul>
              )}
              {entry.data.lineage.merged_from.length > 0 ? (
                <p>
                  {t("lineage.merged")}{" "}
                  <span className="mono">{entry.data.lineage.merged_from.join(", ")}</span>
                </p>
              ) : null}
              {entry.data.lineage.notes.map((n) => (
                <p key={n} className="muted">
                  {n}
                </p>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
