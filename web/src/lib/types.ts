/**
 * The shapes the Python side sends.
 *
 * Hand-written rather than generated: the API is small, and a type that says
 * `dedup_key` is the identifier -- with a comment explaining that it is a
 * stripped URL -- is worth more here than a faithful mechanical translation.
 */

export type ApplicationStatus =
  | 'new'
  | 'applied'
  | 'interview'
  | 'offer'
  | 'rejected'
  | 'skipped';

export const BOARD_ORDER: ApplicationStatus[] = [
  'new',
  'applied',
  'interview',
  'offer',
  'rejected',
  'skipped',
];

export type ColumnKind =
  | 'text'
  | 'note'
  | 'date'
  | 'url'
  | 'number'
  | 'tags'
  | 'checkbox'
  | 'status';

export interface Posting {
  source_id: string;
  title: string;
  url: string;
  company: string;
  location: string;
  region: string;
  workplace: 'onsite' | 'hybrid' | 'remote' | 'unknown';
  description: string;
  employment_type: string;
  education: string;
  salary: string;
  posted_at: string | null;
  deadline: string | null;
  tags: string[];
}

export interface JobRow {
  /** The normalised URL. Everything addresses a job by this. */
  dedup_key: string;
  posting: Posting;
  found_at: string;
  category: string;
  note: string;
  status: ApplicationStatus;
  user_values: Record<string, unknown>;
  link_text: string;
}

export interface ParamChoice {
  value: string;
  label: string;
}

export interface ParamSpec {
  name: string;
  label: string;
  kind: 'text' | 'url' | 'number' | 'boolean' | 'select' | 'multiselect';
  required: boolean;
  default: unknown;
  choices: ParamChoice[];
  placeholder: string;
  help: string;
}

export interface SourceHealth {
  source_id: string;
  last_ok: string | null;
  last_error: string | null;
  last_count: number;
  message: string;
}

export interface SourceManifest {
  id: string;
  name: string;
  homepage: string;
  description: string;
  country: string | null;
  params: ParamSpec[];
  rate_limit: number;
  supports_enrich: boolean;
  needs_credentials: boolean;
  is_global: boolean;
  health: SourceHealth | null;
}

export interface KeywordGroup {
  name: string;
  terms: string[];
}

export interface SearchProfile {
  keyword_groups: KeywordGroup[];
  locations: string[];
  regions: string[];
  remote_terms: string[];
  max_age_days: number;
  excluded_employers: string[];
  excluded_employment_types: string[];
  excluded_schedules: string[];
  employment_type_allowlist: string[];
  description_match_requires: string[];
  flags: Record<string, string[]>;
}

export const EMPTY_PROFILE: SearchProfile = {
  keyword_groups: [],
  locations: [],
  regions: [],
  remote_terms: ['remote', 'work from home', 'hybrid', 'telecommute'],
  max_age_days: 30,
  excluded_employers: [],
  excluded_employment_types: [],
  excluded_schedules: [],
  employment_type_allowlist: [],
  description_match_requires: [],
  flags: {},
};

export type RunPhase = 'running' | 'done' | 'failed' | 'cancelled';

export interface RunSummary {
  id: string;
  phase: RunPhase;
  started_at: string;
  sources: string[];
  lines: string[];
  error: string;
  fetched: number;
  duplicates: number;
  new: number;
  rejected: number;
  errors: Record<string, string>;
  harvested: Record<string, number>;
}

export interface RejectedAd {
  title: string;
  company: string;
  url: string;
  source: string;
  code: string;
  detail: string;
}

export interface RunResults {
  id: string;
  rows: JobRow[];
  rejected: RejectedAd[];
}

export interface ColumnSpec {
  key: string;
  label: string;
  kind: ColumnKind;
  width: number;
  wrap: boolean;
  user_owned: boolean;
}

export interface ConditionalRule {
  column: string;
  equals: string;
  colour: string;
  bold: boolean;
  stop_if_true: boolean;
}

export interface SheetLayout {
  sheet_name: string;
  columns: ColumnSpec[];
  theme: string;
  freeze_header: boolean;
  autofilter: boolean;
  zebra: boolean;
  rules: ConditionalRule[];
}

export interface ExcelTheme {
  value: string;
  default: boolean;
  header_fill: string;
  header_text: string;
  zebra_fill: string;
  border: string;
  link: string;
}

export interface LayoutVocabulary {
  kinds: { value: ColumnKind; label: string }[];
  source_keys: string[];
  themes: ExcelTheme[];
}

export interface PostingPage {
  total: number;
  limit: number;
  offset: number;
  rows: JobRow[];
}

export interface Board {
  order: ApplicationStatus[];
  counts: Record<ApplicationStatus, number>;
  columns: Record<ApplicationStatus, JobRow[]>;
}

export interface HistoryStep {
  at: string;
  from_status: ApplicationStatus;
  to_status: ApplicationStatus;
  note: string;
}

export interface AppSettings {
  version: string;
  python: string;
  platform: string;
  home: string;
  workbook: string;
  workbook_exists: boolean;
  workbook_locked: boolean;
  database: string;
  backups: string;
  keep_backups: number;
  sources_installed: number;
}

export interface WorkbookState {
  path: string;
  exists: boolean;
  locked: boolean;
  message: string;
  backups: string;
}

export interface ExportReport {
  path: string;
  rows: number;
  user_values: number;
  backup: string | null;
  adopted_from_workbook: string[];
}
