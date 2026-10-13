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

export interface Conformance {
  dataset: string;
  dataset_note: string;
  report_id: string;
  scores: Score[];
  families: FamilySummary[];
  score_definition: string;
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
