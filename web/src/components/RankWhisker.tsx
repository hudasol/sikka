import { useTranslation } from "react-i18next";

import { formatNumber } from "../lib/format";
import { useSettings } from "../lib/settings";

interface Props {
  rank: number;
  low: number;
  high: number;
  max: number;
}

// One row of a rank interval chart: the 90 percent interval as a line with end
// caps and the point rank as a square. Rank 1 is at the start of the line.
// The numbers are always printed next to it, so the table is its own alternative.
export function RankWhisker({ rank, low, high, max }: Props) {
  const { t } = useTranslation();
  const settings = useSettings();
  const width = 140;
  const pad = 6;
  const rtl = settings.lang === "ar";
  const x = (v: number) => {
    const share = (v - 1) / Math.max(1, max - 1);
    const pos = pad + share * (width - 2 * pad);
    return rtl ? width - pos : pos;
  };
  const label = t("blackspots.whisker_label", {
    rank: formatNumber(rank, settings),
    low: formatNumber(low, settings),
    high: formatNumber(high, settings),
  });
  return (
    <span className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
      <svg width={width} height={16} role="img" aria-label={label}>
        <line x1={pad} x2={width - pad} y1={8} y2={8} stroke="var(--muted)" strokeDasharray="2 3" />
        <line
          x1={x(low)}
          x2={x(high)}
          y1={8}
          y2={8}
          stroke="var(--accent-strong)"
          strokeWidth={3}
        />
        <line x1={x(low)} x2={x(low)} y1={3} y2={13} stroke="var(--ink)" strokeWidth={2} />
        <line x1={x(high)} x2={x(high)} y1={3} y2={13} stroke="var(--ink)" strokeWidth={2} />
        <rect x={x(rank) - 3.5} y={4.5} width={7} height={7} fill="var(--ink)" />
      </svg>
      <span className="num muted">
        {formatNumber(low, settings)} {t("common.to")} {formatNumber(high, settings)}
      </span>
    </span>
  );
}
