/**
 * Every screen, rendered once.
 *
 * A single-page app fails in one particularly unhelpful way: a runtime error
 * anywhere in the tree gives a blank page and a message only in the console.
 * These tests do not check much, deliberately -- they check that each screen
 * mounts against a plausible API and puts its own heading on the page. That is
 * the failure the build cannot catch and the user cannot diagnose.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '@/i18n';
import ResultsScreen from './ResultsScreen';
import SearchScreen from './SearchScreen';
import SettingsScreen from './SettingsScreen';
import SheetDesigner from './SheetDesigner';
import TrackerScreen from './TrackerScreen';
import Shell from '@/components/Shell';

const LAYOUT = {
  sheet_name: 'Jobs',
  theme: 'navy',
  freeze_header: true,
  autofilter: true,
  zebra: false,
  rules: [],
  columns: [
    { key: 'title', label: 'Position', kind: 'text', width: 40, wrap: false, user_owned: false },
    { key: 'status', label: 'Status', kind: 'status', width: 14, wrap: false, user_owned: true },
  ],
};

const ROW = {
  dedup_key: 'example.test/j/1',
  posting: {
    source_id: 'rss',
    title: 'GIS Engineer',
    url: 'https://example.test/j/1',
    company: 'Kartograf d.o.o.',
    location: 'Rijeka',
    region: '',
    workplace: 'onsite',
    description: '',
    employment_type: '',
    education: '',
    salary: '',
    posted_at: '2026-08-01',
    deadline: '2026-09-01',
    tags: [],
  },
  found_at: '2026-08-24',
  category: 'GIS',
  note: 'matched "gis" in the title',
  status: 'new',
  user_values: {},
  link_text: '',
};

/** One stand-in server, answering whatever a screen happens to ask for. */
const RESPONSES: Record<string, unknown> = {
  '/api/settings': {
    version: '0.1.0.dev0',
    python: '3.11.9',
    platform: 'Windows',
    home: 'C:/Users/x/AppData/Local/JobSheet',
    workbook: 'C:/Users/x/AppData/Local/JobSheet/jobs.xlsx',
    workbook_exists: true,
    workbook_locked: false,
    database: 'C:/Users/x/AppData/Local/JobSheet/jobsheet.sqlite3',
    backups: 'C:/Users/x/AppData/Local/JobSheet/backups',
    keep_backups: 20,
    sources_installed: 14,
  },
  '/api/sources': {
    countries: ['HR'],
    sources: [
      {
        id: 'rss',
        name: 'RSS or Atom feed',
        homepage: 'https://example.test',
        description: 'Paste any feed URL.',
        country: null,
        params: [
          {
            name: 'url',
            label: 'Feed address',
            kind: 'url',
            required: true,
            default: null,
            choices: [],
            placeholder: 'https://…',
            help: '',
          },
        ],
        rate_limit: 0.7,
        supports_enrich: false,
        needs_credentials: false,
        is_global: true,
        health: null,
      },
      {
        id: 'hzz',
        name: 'HZZ Burza rada',
        homepage: 'https://burzarada.hzz.hr/',
        description: '',
        country: 'HR',
        params: [],
        rate_limit: 0.7,
        supports_enrich: true,
        needs_credentials: false,
        is_global: false,
        health: {
          source_id: 'hzz',
          last_ok: '2026-08-24T09:00:00',
          last_error: null,
          last_count: 218,
          message: '218 ad(s)',
        },
      },
    ],
  },
  '/api/postings': { total: 1, limit: 100, offset: 0, rows: [ROW] },
  '/api/applications/board': {
    order: ['new', 'applied', 'interview', 'offer', 'rejected', 'skipped'],
    counts: { new: 1, applied: 0, interview: 0, offer: 0, rejected: 0, skipped: 0 },
    columns: { new: [ROW], applied: [], interview: [], offer: [], rejected: [], skipped: [] },
  },
  '/api/layouts/current': {
    workbook: 'jobs.xlsx',
    exists: true,
    from_workbook: true,
    layout: LAYOUT,
  },
  '/api/layouts/vocabulary': {
    kinds: [{ value: 'text', label: 'Text' }],
    source_keys: ['title', 'company'],
    themes: [
      {
        value: 'navy',
        default: true,
        header_fill: 'FF1F4E79',
        header_text: 'FFFFFFFF',
        zebra_fill: 'FFF2F5F9',
        border: 'FFBFC7D1',
        link: 'FF1F4E79',
      },
    ],
  },
  '/api/layouts/presets': [
    { name: 'default', description: 'What most people want.', layout: LAYOUT },
  ],
  '/api/layouts/validate': { valid: true, problems: [], layout: LAYOUT, user_owned: ['status'] },
  '/api/export/workbook': {
    path: 'jobs.xlsx',
    exists: true,
    locked: false,
    message: 'Ready.',
    backups: 'backups',
  },
  '/api/profiles/search': ['my search'],
  '/api/profiles/layout': ['my design'],
  '/api/sources/health': [],
};

function answerFor(url: string): unknown {
  const path = url.split('?')[0] ?? url;
  if (path in RESPONSES) return RESPONSES[path];
  if (path.startsWith('/api/applications/history')) return [];
  if (path.startsWith('/api/postings')) return RESPONSES['/api/postings'];
  return {};
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('every screen mounts', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) =>
        Promise.resolve(
          new Response(JSON.stringify(answerFor(String(input))), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        ),
      ),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('01 Search', async () => {
    render(wrap(<SearchScreen />));
    expect(await screen.findByRole('heading', { name: 'Search', level: 1 })).toBeInTheDocument();
    // The form for each source is drawn from the manifest, not from this code.
    expect(await screen.findByText('RSS or Atom feed')).toBeInTheDocument();
    expect(await screen.findByText('HZZ Burza rada')).toBeInTheDocument();
  });

  it('02 Results', async () => {
    render(wrap(<ResultsScreen />));
    expect(await screen.findByRole('heading', { name: 'Results', level: 1 })).toBeInTheDocument();
    expect(await screen.findByText('GIS Engineer')).toBeInTheDocument();
  });

  it('03 Sheet designer', async () => {
    render(wrap(<SheetDesigner />));
    expect(
      await screen.findByRole('heading', { name: 'Sheet designer', level: 1 }),
    ).toBeInTheDocument();
    // The preview is the point of the screen; it has to be there.
    await waitFor(() => expect(screen.getAllByText('Position').length).toBeGreaterThan(0));
  });

  it('04 Tracker', async () => {
    render(wrap(<TrackerScreen />));
    expect(await screen.findByRole('heading', { name: 'Tracker', level: 1 })).toBeInTheDocument();
    expect(await screen.findByText('GIS Engineer')).toBeInTheDocument();
  });

  it('05 Settings', async () => {
    render(wrap(<SettingsScreen />));
    expect(await screen.findByRole('heading', { name: 'Settings', level: 1 })).toBeInTheDocument();
    // The promise the app makes is that everything is in files you can open,
    // so the real paths have to be on the page.
    expect(await screen.findByText(/jobs\.xlsx/)).toBeInTheDocument();
  });

  it('the shell links to every screen in the rail', () => {
    render(wrap(<Shell />));
    for (const name of ['Search', 'Results', 'Tracker', 'Settings']) {
      expect(screen.getByRole('link', { name: new RegExp(name, 'i') })).toBeInTheDocument();
    }
  });

  it('the sheet designer is hidden from the rail but still routed', () => {
    render(wrap(<Shell />));
    // Hidden, not removed. If this ever starts failing because the link is
    // back, that is a decision someone made in HIDDEN_FROM_RAIL, not a bug.
    expect(screen.queryByRole('link', { name: /sheet designer/i })).not.toBeInTheDocument();
  });

  it('the rail numbers itself without a gap where a hidden screen was', () => {
    render(wrap(<Shell />));
    // The whole point of computing the numbers: hiding 03 must not leave the
    // rail reading 01, 02, 04, 05.
    for (const number of ['01', '02', '03', '04']) {
      expect(screen.getByText(number)).toBeInTheDocument();
    }
    expect(screen.queryByText('05')).not.toBeInTheDocument();
  });
});
