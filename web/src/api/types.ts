// Response types of the Sikka API (and of the static snapshot, which mirrors it).

export interface Health {
  status: string;
  version: string;
  mode: "live" | "static";
  contract_version: string;
  notice: string;
}

export interface Score {
  producer_id: string;
  family: string;
  family_name: string;
  passing: number;
  total: number;
  estimate: number;
  low: number;
  high: number;
}

export interface FamilySummary {
  family: string;
  name: string;
  rules_evaluated: number;
  rules_failing: number;
  findings: number;
}

export interface Example {
  row: number | null;
  record_id: string | null;
  detail: string;
}

export interface RuleResult {
  rule_id: string;
  family: string;
  title: string;
  title_ar?: string;
  share_low?: number;
  share_high?: number;
  severity: "error" | "warning" | "info";
  scope: "record" | "series" | "file";
  status: "evaluated" | "skipped";
  note: string;
  file: string;
  producer_id: string | null;
  findings: number;
  records: number;
  series: number;
  share: number;
  fields: string[];
  examples: Example[];
  locations: [number, number, number][];
  fix_hint: string;
}

export interface FileSummary {
  file: string;
  feed_type: string | null;
  producer_id: string | null;
  format: string;
  rows: number;
  header_error: string | null;
  quarantined_rows: number;
}

export interface Report {
  report_id: string;
  notice: string;
  contract_version: string;
  engine_version: string;
  files: FileSummary[];
  references: string[];
  families: FamilySummary[];
  rules: RuleResult[];
  rules_failing: number;
  scores: Score[];
  file_checks: { file: string; producer_id: string; rule_id: string; findings: number }[];
  score_definition: string;
}

export interface TrendPoint {
  producer_id: string;
  period: string;
  passing: number;
  total: number;
  estimate: number;
  low: number;
  high: number;
}

export interface Conformance {
  dataset: string;
  dataset_note: string;
  report_id: string;
  scores: Score[];
  families: FamilySummary[];
  score_definition: string;
  trend: TrendPoint[];
  file_checks: { file: string; producer_id: string; rule_id: string; findings: number }[];
  headline: {
    producers: number;
    conforming_threshold: number;
    producers_conforming: number;
    producers_conforming_low: number;
    producers_conforming_high: number;
    rules_failing: number;
    rules_total: number;
    records_total: number;
    flagged_record_findings: number;
  };
}

export interface Sample {
  name: string;
  set: "clean" | "broken";
  file: string;
  bytes: number;
  report_id?: string;
}

export interface ValidateResponse {
  report_id: string;
  notice: string;
}

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
}

export interface FieldSpec {
  feed: string;
  name: string;
  type: string;
  required: boolean;
  unit: string | null;
  allowed: string | null;
  description_en: string;
  description_ar: string;
  example: unknown;
}

export interface ContractBundle {
  version: string;
  status: string;
  summary: string;
  conventions: Record<string, string>;
  prohibited_fields: string[];
  feeds: Record<
    string,
    { title_en: string; title_ar: string; schema: string; fields: FieldSpec[] }
  >;
}

export interface ContractIndex {
  current: string;
  versions: { version: string; status: string; summary: string }[];
  bundle: ContractBundle;
}

export interface ContractChange {
  feed: string;
  field: string;
  kind: string;
  impact: string;
  detail: string;
}

export interface ContractDiff {
  old: string;
  new: string;
  required_bump: string | null;
  declared_bump: string | null;
  compatible: boolean;
  changes: ContractChange[];
}

export interface RuleInfo {
  id: string;
  family: string;
  family_name: string;
  title: string;
  title_ar?: string;
  severity: "error" | "warning" | "info";
  description: string;
  rationale: string;
  fix_hint: string;
  feed_types: string[];
  fields: string[];
  scope: string;
}

export interface FaultInfo {
  id: string;
  title: string;
  title_ar?: string;
  description: string;
  feed_types: string[];
  unit: string;
  expected_rules: string[];
}

export interface RankOnly {
  rank: number | null;
  rank_low: number | null;
  rank_high: number | null;
  p_top_k: number | null;
}

export interface SegmentRow {
  segment_id: string;
  corridor: string;
  road_name_en: string;
  road_name_ar: string;
  road_class: string;
  lane_count: number;
  length_km: number;
  owner: string;
  aadt: number | null;
  window_years: number;
  observed: number;
  observed_by_year: Record<string, number>;
  unresolved_pairs: number;
  coverage: number;
  abstained: string | null;
  predicted_per_year: number | null;
  eb_weight: number | null;
  eb_per_year: number | null;
  psi_per_year: number | null;
  rank: number | null;
  rank_median: number | null;
  rank_low: number | null;
  rank_high: number | null;
  p_top_k: number | null;
  quality_factor: number | null;
  eb_only: RankOnly;
  raw_rank: number | null;
  rate_rank: number | null;
  rate_per_mvkm: number | null;
}

export interface SpfSummary {
  coefficients: { name: string; estimate: number; std_error: number }[];
  alpha: number;
  k: number;
  pseudo_r2_mcfadden: number;
  pearson_dispersion: number;
  n_segments: number;
}

export interface CaptureRecapture {
  group: string;
  owner_reports: number;
  partner_reports: number;
  both: number;
  seen_by_either: number;
  estimated_total: number;
  estimated_total_low: number;
  estimated_total_high: number;
  completeness: number;
}

export interface RankingSummary {
  published: {
    method: string;
    segments: number;
    ranked: number;
    abstained: number;
    abstained_by_reason: Record<string, number>;
    top_k: number;
    draws: number;
    interval: number;
  };
  eb_only: { ranked: number; abstained: number };
  spf: SpfSummary | null;
  capture_recapture: CaptureRecapture[];
  window: { first_year: number; last_year: number };
}

export interface Ranking {
  dataset: string;
  notice: string;
  summary: RankingSummary;
  segments: SegmentRow[];
}

export interface Explanation {
  kind: "ranked" | "abstained";
  reasons?: string[];
  observed_per_year?: number;
  predicted_per_year?: number;
  ratio?: number | null;
  eb_weight?: number | null;
  eb_per_year?: number | null;
  psi_per_year?: number | null;
  rank?: number | null;
  rank_low?: number | null;
  rank_high?: number | null;
  p_top_k?: number | null;
  unresolved_pairs?: number;
  quality_factor?: number | null;
}

export interface SegmentDetail extends SegmentRow {
  dataset: string;
  explanation: Explanation;
  geometry: { type: "LineString"; coordinates: [number, number][] } | null;
  clean_comparison: SegmentRow | null;
}

export interface LineageItem {
  canonical_id: string;
  kind: "crash" | "exposure" | "segment";
  segment_id: string | null;
  status: string;
  sources: number;
  record_ids: string[];
}

export interface LineageEntry {
  canonical_id: string;
  kind: string;
  record: Record<string, unknown>;
  lineage: {
    sources: { producer_id: string; file: string; row: number; record_id: string | null }[];
    adapter: string;
    adapter_version: string;
    transformations: {
      step: string;
      field: string;
      before: unknown;
      after: unknown;
      note: string;
    }[];
    findings: { rule_id: string; field: string | null; detail: string | null }[];
    status: string;
    merged_from: string[];
    notes: string[];
  };
}

export interface Verdict {
  id: string;
  experiment: string;
  text: string;
  observed: string;
  verdict: "HIT" | "MISS" | "PENDING";
}

export interface Summary {
  estimate: number | null;
  low: number | null;
  high: number | null;
  n: number;
}

export interface MethodInfo {
  notice: string;
  ranking: RankingSummary;
  results: {
    predictions?: { predictions: Verdict[] };
    e1_fault_detection?: {
      seeds: number[];
      rates: number[];
      faults: Record<
        string,
        {
          title: string;
          by_rate: Record<string, { recall: Summary; precision: Summary }>;
          schema_baseline_recall?: Summary;
          combined?: { recall: Summary; precision_any: Summary };
        }
      >;
    };
    e2_entity_resolution?: {
      seeds: number[];
      summary: Record<string, Record<string, Summary>>;
      naive_baseline: Record<string, Record<string, Summary>>;
    };
    e3_blackspot_ranking?: {
      seeds: number[];
      top_k: number;
      methods: string[];
      summary: Record<string, Summary>;
    };
    e4_robustness?: {
      seeds: number[];
      scenarios: string[];
      summary: Record<string, Record<string, Record<string, Summary>>>;
    };
    e5_tasking?: {
      seeds: number[];
      strategies: string[];
      summary: Record<string, Summary>;
    };
  };
}
