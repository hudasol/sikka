import { useId } from "react";
import { useTranslation } from "react-i18next";

import { formatInterval, formatPercent } from "../lib/format";
import { useSettings } from "../lib/settings";

export interface IntervalItem {
  label: string;
  estimate: number;
  low: number;
  high: number;
}

interface Props {
  items: IntervalItem[];
  title: string;
  ariaLabel: string;
  domain?: [number, number];
  valueLabel?: string;
}

// Whisker chart: a point with its interval for every item. Every chart is paired
// with a table holding the same numbers, for screen readers and for printing.
export function IntervalChart({ items, title, ariaLabel, domain = [0, 1], valueLabel }: Props) {
  const { t } = useTranslation();
  const settings = useSettings();
  const id = useId();
  const rowH = 26;
  const labelW = 210;
  const width = 640;
  const plotW = width - labelW - 20;
  const height = items.length * rowH + 30;
  const rtl = settings.lang === "ar";
  const x = (v: number) => {
    const share = (v - domain[0]) / (domain[1] - domain[0]);
    const clamped = Math.min(1, Math.max(0, share));
    return rtl ? width - labelW - clamped * plotW : labelW + clamped * plotW;
  };
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => domain[0] + f * (domain[1] - domain[0]));
  return (
    <figure style={{ margin: 0 }}>
      <svg
        className="whisker-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby={`${id}-title`}
      >
        <title id={`${id}-title`}>{ariaLabel}</title>
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={x(tick)}
              x2={x(tick)}
              y1={0}
              y2={height - 20}
              stroke="var(--muted)"
              strokeDasharray="2 4"
            />
            <text
              x={x(tick)}
              y={height - 4}
              fontSize="11"
              textAnchor="middle"
              fill="var(--muted-text)"
            >
              {formatPercent(tick, settings, 0)}
            </text>
          </g>
        ))}
        {items.map((item, i) => {
          const y = i * rowH + 14;
          return (
            <g key={item.label}>
              <text
                x={rtl ? width - 8 : 8}
                y={y + 4}
                fontSize="12"
                fill="var(--text)"
                textAnchor={rtl ? "end" : "start"}
              >
                {item.label}
              </text>
              <line
                x1={x(item.low)}
                x2={x(item.high)}
                y1={y}
                y2={y}
                stroke="var(--accent-strong)"
                strokeWidth="3"
              />
              <line
                x1={x(item.low)}
                x2={x(item.low)}
                y1={y - 6}
                y2={y + 6}
                stroke="var(--ink)"
                strokeWidth="2"
              />
              <line
                x1={x(item.high)}
                x2={x(item.high)}
                y1={y - 6}
                y2={y + 6}
                stroke="var(--ink)"
                strokeWidth="2"
              />
              <rect x={x(item.estimate) - 4} y={y - 4} width="8" height="8" fill="var(--ink)" />
            </g>
          );
        })}
      </svg>
      <figcaption className="visually-hidden">{title}</figcaption>
      <details>
        <summary>{t("common.table")}</summary>
        <div className="details-body table-wrap">
          <table>
            <caption className="visually-hidden">{title}</caption>
            <thead>
              <tr>
                <th scope="col">{title}</th>
                <th scope="col">{valueLabel ?? t("common.share_passing")}</th>
                <th scope="col">{t("common.interval")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.label}>
                  <th scope="row">{item.label}</th>
                  <td className="num">{formatPercent(item.estimate, settings)}</td>
                  <td className="num">{formatInterval(item.low, item.high, settings)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
