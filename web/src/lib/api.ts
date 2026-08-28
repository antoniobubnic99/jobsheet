/**
 * Talking to the local JobSheet process.
 *
 * The token comes from the page itself -- the server writes it into the HTML it
 * serves, which is the one place a cross-origin page cannot read. Every call
 * carries it in a header; only the progress stream falls back to a query
 * parameter, because `EventSource` cannot set headers.
 *
 * Errors are turned into a real `ApiError` carrying the server's own sentence.
 * The Python side writes those sentences for people ("jobs.xlsx is open in
 * Excel. Close it and run again"), so the interface shows them verbatim rather
 * than inventing a worse one.
 *
 * Sign-in errors are the exception, and carry a `code` as well. Those are the
 * few messages somebody reads in a hurry, in their own language, while
 * wondering whether they have just been locked out of their own laptop -- so
 * the interface translates them and keeps the server's sentence as the
 * fallback for any code it has not been taught.
 *
 * The session rides in an HttpOnly cookie, which is why nothing here handles
 * one: the browser attaches it and no script, ours included, can read it.
 */

import type {
  Account,
  AppSettings,
  AuthStatus,
  Board,
  DbRun,
  ExportReport,
  FolderListing,
  HistoryStep,
  JobRow,
  LayoutVocabulary,
  PlaceSuggestions,
  PostingPage,
  RunResults,
  RunSummary,
  SearchProfile,
  SearchSetup,
  SeenCompany,
  SheetLayout,
  SourceHealth,
  SourceManifest,
  SourceProgress,
  WorkbookChange,
  WorkbookState,
} from './types';

declare global {
  interface Window {
    __JOBSHEET__?: { token: string; version: string };
  }
}

export const TOKEN_HEADER = 'X-JobSheet-Token';

/** Saved searches, saved sheet designs, and the one setup the wizard writes. */
export type ProfileKind = 'search' | 'layout' | 'setup';

/** The name the wizard's setup is stored under, one per account. */
export const DEFAULT_SETUP = 'default';

export function sessionToken(): string {
  return window.__JOBSHEET__?.token ?? '';
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** Empty unless the server sent one; see the note at the top of this file. */
    readonly code: string = '',
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** The short constant an auth failure carries, when it carries one. */
function readCode(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'code' in detail) {
      return String((detail as { code: unknown }).code);
    }
  }
  return '';
}

/** FastAPI puts the message in `detail`, which is sometimes a list of problems. */
function readDetail(body: unknown, fallback: string): string {
  if (typeof body === 'string') return body;
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'message' in detail) {
      return String((detail as { message: unknown }).message);
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          item && typeof item === 'object' && 'message' in item
            ? String((item as { message: unknown }).message)
            : item && typeof item === 'object' && 'msg' in item
              ? `${((item as { loc?: unknown[] }).loc ?? []).join('.')}: ${String((item as { msg: unknown }).msg)}`
              : String(item),
        )
        .join('; ');
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      [TOKEN_HEADER]: sessionToken(),
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = await response.text().catch(() => null);
    }
    throw new ApiError(
      response.status,
      readDetail(body, `${response.status} ${response.statusText}`),
      readCode(body),
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** For the export endpoints, which hand back a file rather than JSON. */
async function download(path: string, body: unknown, filename: string): Promise<void> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', [TOKEN_HEADER]: sessionToken() },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

const query = (params: Record<string, string | number | undefined>): string => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
};

export const api = {
  settings: () => request<AppSettings>('/api/settings'),
  /** The folders inside one folder, for the picker. Empty path = where to start. */
  folders: (path = '') => request<FolderListing>(`/api/settings/folders${query({ path })}`),
  /** Point this account at a different workbook, optionally taking the file along. */
  setWorkbook: (path: string, move = false) =>
    request<WorkbookChange>('/api/settings/workbook', {
      method: 'PUT',
      body: JSON.stringify({ path, move }),
    }),

  // ---- who is here ------------------------------------------------------
  auth: {
    /** Safe before signing in: it is what decides which form to show. */
    status: () => request<AuthStatus>('/api/auth/status'),
    me: () => request<Account>('/api/auth/me'),
    register: (username: string, password: string) =>
      request<Account>('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    /** Take over the data an install had before it had accounts. Once only. */
    claim: (username: string, password: string) =>
      request<Account>('/api/auth/claim', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    login: (username: string, password: string) =>
      request<Account>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    logout: () => request<{ signed_out: boolean }>('/api/auth/logout', { method: 'POST' }),
    changePassword: (current: string, next: string) =>
      request<{ changed: boolean }>('/api/auth/password', {
        method: 'POST',
        body: JSON.stringify({ current, new: next }),
      }),
    finishOnboarding: (setup: SearchSetup, workbook: string) =>
      request<Account>('/api/auth/onboarding', {
        method: 'POST',
        body: JSON.stringify({ setup, workbook }),
      }),
  },

  // ---- what the wizard suggests -----------------------------------------

  /**
   * Places to offer for a location or county field.
   *
   * Served rather than bundled: the table is five hundred names, and the server
   * answering is on this machine. `kind` narrows it -- "county" for the region
   * field, "city" where only a town makes sense, empty for everything.
   */
  places: (q = '', kind: '' | 'city' | 'county' = '') =>
    request<PlaceSuggestions>(`/api/places${query({ q, kind })}`),

  /** Employers this account has already collected ads from. */
  companies: (q = '', limit = 20) =>
    request<{ companies: SeenCompany[]; total: number }>(
      `/api/postings/companies${query({ q, limit })}`,
    ),

  // ---- sources ----------------------------------------------------------
  sources: () =>
    request<{ sources: SourceManifest[]; countries: string[] }>('/api/sources'),
  sourceHealth: () => request<SourceHealth[]>('/api/sources/health'),

  // ---- searching --------------------------------------------------------
  startSearch: (body: {
    sources: { source_id: string; params: Record<string, unknown> }[];
    profile: SearchProfile;
    max_items?: number;
    max_enrich?: number;
  }) =>
    request<RunSummary>('/api/search', { method: 'POST', body: JSON.stringify(body) }),
  run: (id: string) => request<RunSummary>(`/api/search/${id}`),
  runs: () => request<RunSummary[]>('/api/search'),
  results: (id: string) => request<RunResults>(`/api/search/${id}/results`),
  cancelRun: (id: string) =>
    request<{ stopped: boolean }>(`/api/search/${id}/cancel`, { method: 'POST' }),

  /**
   * The live commentary. Returns the unsubscribe function.
   *
   * Two channels on one stream. `progress` is the prose; `state` is one
   * source's position, which is what the bars are drawn from. Both replay from
   * the start when a page reconnects, so a reload mid-search does not come back
   * to an empty log and empty bars.
   */
  watchRun(
    id: string,
    onLine: (line: string) => void,
    onEnd: (phase: string) => void,
    onState?: (progress: SourceProgress) => void,
  ): () => void {
    const source = new EventSource(
      `/api/search/${id}/stream?token=${encodeURIComponent(sessionToken())}`,
    );
    source.addEventListener('progress', (event) => onLine((event as MessageEvent).data));
    source.addEventListener('state', (event) => {
      if (!onState) return;
      try {
        onState(JSON.parse((event as MessageEvent).data) as SourceProgress);
      } catch {
        // A malformed frame costs one bar update. It must never take down the
        // stream, which is also carrying the log the user is reading.
      }
    });
    source.addEventListener('end', (event) => {
      onEnd((event as MessageEvent).data);
      source.close();
    });
    // A dropped connection would otherwise have EventSource reconnect forever
    // against a run that has already finished.
    source.onerror = () => source.close();
    return () => source.close();
  },

  // ---- collected jobs ---------------------------------------------------
  postings: (params: {
    q?: string;
    status?: string;
    source?: string;
    /** The `runs` row id, to narrow the table to one search. */
    run?: string;
    limit?: number;
    offset?: number;
  }) => request<PostingPage>(`/api/postings${query(params)}`),
  /** Past searches as recorded on disk. These outlive the process; `runs()` does not. */
  searchRuns: (limit = 20) =>
    request<DbRun[]>(`/api/postings/runs${query({ limit })}`),
  posting: (dedupKey: string) =>
    request<JobRow>(`/api/postings/one${query({ dedup_key: dedupKey })}`),
  forget: (dedupKey: string) =>
    request<{ deleted: string }>(`/api/postings/one${query({ dedup_key: dedupKey })}`, {
      method: 'DELETE',
    }),

  // ---- the board --------------------------------------------------------
  board: () => request<Board>('/api/applications/board'),
  move: (dedup_key: string, status: string, note = '') =>
    request<{ changed: boolean }>('/api/applications/status', {
      method: 'POST',
      body: JSON.stringify({ dedup_key, status, note }),
    }),
  history: (dedupKey: string) =>
    request<HistoryStep[]>(`/api/applications/history${query({ dedup_key: dedupKey })}`),

  // ---- the sheet design -------------------------------------------------
  vocabulary: () => request<LayoutVocabulary>('/api/layouts/vocabulary'),
  presets: () =>
    request<{ name: string; description: string; layout: SheetLayout }[]>(
      '/api/layouts/presets',
    ),
  currentLayout: () =>
    request<{
      workbook: string;
      exists: boolean;
      from_workbook: boolean;
      layout: SheetLayout;
    }>('/api/layouts/current'),
  validateLayout: (layout: SheetLayout) =>
    request<{
      valid: boolean;
      problems: { where: string; message: string }[];
      user_owned?: string[];
    }>('/api/layouts/validate', { method: 'POST', body: JSON.stringify(layout) }),

  // ---- saved profiles ---------------------------------------------------
  profiles: (kind: ProfileKind) => request<string[]>(`/api/profiles/${kind}`),
  loadProfile: <T>(kind: ProfileKind, name: string) =>
    request<{ name: string; payload: T }>(
      `/api/profiles/${kind}/${encodeURIComponent(name)}`,
    ),
  saveProfile: (kind: ProfileKind, name: string, payload: unknown) =>
    request<{ name: string }>(`/api/profiles/${kind}/${encodeURIComponent(name)}`, {
      method: 'PUT',
      body: JSON.stringify({ payload }),
    }),
  deleteProfile: (kind: ProfileKind, name: string) =>
    request<{ deleted: string }>(`/api/profiles/${kind}/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    }),

  // ---- getting it out ---------------------------------------------------
  workbookState: () => request<WorkbookState>('/api/export/workbook'),
  exportWorkbook: (body: { layout?: SheetLayout; statuses?: string[] }) =>
    request<ExportReport>('/api/export/xlsx', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  downloadCsv: (body: { layout?: SheetLayout; statuses?: string[] }) =>
    download('/api/export/csv', body, 'jobs.csv'),
  downloadJson: (body: { statuses?: string[] }) =>
    download('/api/export/json', body, 'jobs.json'),

  // ---- the letter -------------------------------------------------------
  letter: (body: {
    dedup_key: string;
    applicant?: { name: string; email: string; phone: string; pitch: string };
    template?: string | null;
  }) =>
    request<{ dedup_key: string; title: string; text: string }>('/api/letter', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};
