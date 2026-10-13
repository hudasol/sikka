import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { getJson } from "../api/client";
import type { ContractBundle, ContractDiff, ContractIndex, RuleInfo } from "../api/types";
import { SeverityBadge } from "../components/SeverityBadge";
import { ErrorState, Loading } from "../components/States";
import { useSettings } from "../lib/settings";

export function Contract() {
  const { t } = useTranslation();
  const settings = useSettings();
  const index = useQuery({
    queryKey: ["contract"],
    queryFn: () => getJson<ContractIndex>("/v1/contract"),
  });
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => getJson<RuleInfo[]>("/v1/rules") });
  const [version, setVersion] = useState<string | null>(null);
  const current = version ?? index.data?.current ?? "1.0.0";
  const bundle = useQuery({
    queryKey: ["contract", current],
    queryFn: () => getJson<ContractBundle>(`/v1/contract/${current}`),
    enabled: index.isSuccess,
  });
  const [feed, setFeed] = useState("crash_records");
  const rulesByField = useMemo(() => {
    const out = new Map<string, RuleInfo[]>();
    for (const rule of rules.data ?? []) {
      for (const feedType of rule.feed_types) {
        for (const field of rule.fields) {
          const key = `${feedType}.${field}`;
          out.set(key, [...(out.get(key) ?? []), rule]);
        }
      }
    }
    return out;
  }, [rules.data]);

  return (
    <section aria-labelledby="contract-title">
      <h1 id="contract-title">{t("contract.title")}</h1>
      <p>{t("contract.intro")}</p>
      <p className="muted">{t("contract.arabic_note")}</p>
      {index.isPending ? <Loading /> : null}
      {index.isError ? <ErrorState error={index.error} /> : null}
      {index.data ? (
        <div className="card soft row">
          <label>
            {t("contract.version")}{" "}
            <select value={current} onChange={(e) => setVersion(e.target.value)}>
              {index.data.versions.map((v) => (
                <option key={v.version} value={v.version}>
                  {v.version} ({t(`contract.status_${v.status}`)})
                </option>
              ))}
            </select>
          </label>
          <div role="tablist" aria-label={t("contract.feeds")} className="row">
            {Object.keys(index.data.bundle.feeds).map((f) => (
              <button
                key={f}
                type="button"
                role="tab"
                aria-selected={feed === f}
                className={feed === f ? "primary" : undefined}
                onClick={() => setFeed(f)}
              >
                {t(`feed.${f}`)}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {bundle.data ? (
        <div className="card" role="tabpanel" aria-label={t(`feed.${feed}`)}>
          <h2>
            {t(`feed.${feed}`)} <span className="muted mono">v{bundle.data.version}</span>
          </h2>
          <div className="table-wrap">
            <table data-testid="field-dictionary">
              <thead>
                <tr>
                  <th scope="col">{t("contract.field")}</th>
                  <th scope="col">{t("contract.type")}</th>
                  <th scope="col">{t("contract.unit")}</th>
                  <th scope="col">{t("contract.allowed")}</th>
                  <th scope="col">{t("contract.required")}</th>
                  <th scope="col">{t("contract.description_en")}</th>
                  <th scope="col">{t("contract.description_ar")}</th>
                  <th scope="col">{t("contract.example")}</th>
                  <th scope="col">{t("contract.rules")}</th>
                </tr>
              </thead>
              <tbody>
                {(bundle.data.feeds[feed]?.fields ?? []).map((f) => (
                  <tr key={f.name}>
                    <th scope="row" className="mono">
                      {f.name}
                    </th>
                    <td>{f.type}</td>
                    <td>{f.unit ?? ""}</td>
                    <td lang="en" dir="ltr">
                      {f.allowed ?? ""}
                    </td>
                    <td>{f.required ? t("contract.yes") : t("contract.no")}</td>
                    <td lang="en" dir="ltr">
                      {f.description_en}
                    </td>
                    <td lang="ar" dir="rtl">
                      {f.description_ar}
                    </td>
                    <td className="mono" dir="ltr">
                      {JSON.stringify(f.example)}
                    </td>
                    <td>
                      {(rulesByField.get(`${feed}.${f.name}`) ?? []).map((r) => (
                        <a
                          key={r.id}
                          href={`#rule-${r.id}`}
                          className="mono rule-link"
                          title={r.title}
                        >
                          {r.id}{" "}
                        </a>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {index.data ? <DiffView versions={index.data.versions.map((v) => v.version)} /> : null}
      <div className="card">
        <h2>{t("contract.rule_catalogue")}</h2>
        {rules.isPending ? <Loading /> : null}
        {(rules.data ?? []).map((r) => (
          <details key={r.id} id={`rule-${r.id}`}>
            <summary>
              <span className="mono">{r.id}</span>{" "}
              {settings.lang === "ar" ? (r.title_ar ?? r.title) : r.title}{" "}
              <SeverityBadge severity={r.severity} />
            </summary>
            <div className="details-body">
              <p lang="en" dir="ltr">
                {r.description}
              </p>
              <p>
                <strong>{t("contract.why")}</strong>{" "}
                <span lang="en" dir="ltr">
                  {r.rationale}
                </span>
              </p>
              <p>
                <strong>{t("common.fix")}:</strong>{" "}
                <span lang="en" dir="ltr">
                  {r.fix_hint}
                </span>
              </p>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

function DiffView({ versions }: { versions: string[] }) {
  const { t } = useTranslation();
  const [oldV, setOld] = useState(versions[0] ?? "1.0.0");
  const [newV, setNew] = useState(versions[1] ?? versions[0] ?? "1.0.0");
  const diff = useQuery({
    queryKey: ["diff", oldV, newV],
    queryFn: () => getJson<ContractDiff>(`/v1/contract/diff/${oldV}/${newV}`),
    enabled: oldV !== newV,
  });
  return (
    <div className="card">
      <h2>{t("contract.diff")}</h2>
      <div className="row">
        <label>
          {t("contract.from")}{" "}
          <select value={oldV} onChange={(e) => setOld(e.target.value)}>
            {versions.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          {t("contract.to")}{" "}
          <select value={newV} onChange={(e) => setNew(e.target.value)}>
            {versions.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
      </div>
      {oldV === newV ? <p className="muted">{t("contract.same_version")}</p> : null}
      {diff.data ? (
        <>
          <table data-testid="contract-diff">
            <thead>
              <tr>
                <th scope="col">{t("contract.impact")}</th>
                <th scope="col">{t("contract.change")}</th>
                <th scope="col">{t("contract.field")}</th>
                <th scope="col">{t("contract.detail")}</th>
              </tr>
            </thead>
            <tbody>
              {diff.data.changes.map((c) => (
                <tr key={`${c.feed}.${c.field}.${c.detail}`}>
                  <td>{c.impact}</td>
                  <td>{c.kind}</td>
                  <td className="mono">
                    {c.feed}.{c.field}
                  </td>
                  <td>{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            {t("contract.bump", {
              required: diff.data.required_bump ?? "-",
              declared: diff.data.declared_bump ?? "-",
            })}{" "}
            <strong>
              {diff.data.compatible ? t("contract.compatible") : t("contract.incompatible")}
            </strong>
          </p>
        </>
      ) : null}
    </div>
  );
}
