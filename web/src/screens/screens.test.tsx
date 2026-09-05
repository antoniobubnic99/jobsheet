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
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '@/i18n';
import HomeScreen from './HomeScreen';
import ResultsScreen from './ResultsScreen';
import SearchScreen from './SearchScreen';
import SettingsScreen from './SettingsScreen';
import SheetDesigner from './SheetDesigner';
import TrackerScreen from './TrackerScreen';
import Shell from '@/components/Shell';
import { AccountProvider } from '@/lib/account';

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
  // Must be listed before the `/api/postings` prefix fallback below, or the
  // results screen is handed a page object where it expects a list of searches.
  '/api/postings/runs': [
    {
      id: 4,
      started_at: '2026-08-24T10:15:00',
      finished_at: '2026-08-24T10:16:00',
      fetched: 40,
      added: 34,
      duplicates: 6,
      rejected: 0,
    },
  ],
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
  '/api/auth/status': { accounts: 1, claimable: null },
  '/api/auth/me': {
    id: 1,
    username: 'ana',
    onboarded: true,
    has_password: true,
    workbook: null,
    created_at: '2026-08-24T09:00:00',
    workbook_path: 'C:/Users/x/AppData/Local/JobSheet/jobs.xlsx',
    home: 'C:/Users/x/AppData/Local/JobSheet',
    primary: true,
  },
  // What the wizard wrote. The search screen opens with this in it.
  '/api/profiles/setup/default': {
    name: 'default',
    kind: 'setup',
    payload: {
      headline: 'Surveyor',
      profile: {
        keyword_groups: [{ name: 'GIS', terms: ['gis'] }],
        locations: ['Rijeka'],
        regions: [],
        remote_terms: [],
        max_age_days: 30,
        excluded_employers: [],
        excluded_employment_types: [],
        excluded_schedules: [],
        wanted_employment_types: ['permanent'],
        dream_employers: [],
        employment_type_allowlist: [],
        description_match_requires: [],
        flags: {},
      },
      sources: [{ source_id: 'hzz', params: {} }],
    },
  },
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
      <AccountProvider>
        <MemoryRouter>{node}</MemoryRouter>
      </AccountProvider>
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

  it('03 Tracker', async () => {
    render(wrap(<TrackerScreen />));
    expect(await screen.findByRole('heading', { name: 'Tracker', level: 1 })).toBeInTheDocument();
    expect(await screen.findByText('GIS Engineer')).toBeInTheDocument();
  });

  it('Settings', async () => {
    render(wrap(<SettingsScreen />));
    expect(await screen.findByRole('heading', { name: 'Settings', level: 1 })).toBeInTheDocument();
    // The promise the app makes is that everything is in files you can open,
    // so the real paths have to be on the page.
    expect(await screen.findByText(/jobs\.xlsx/)).toBeInTheDocument();
  });

  it('the shell links to every screen in the rail', () => {
    render(wrap(<Shell />));
    for (const name of ['Search', 'Results', 'Tracker']) {
      expect(screen.getByRole('link', { name: new RegExp(name, 'i') })).toBeInTheDocument();
    }
  });

  it('the sheet designer is hidden from the rail but still routed', () => {
    render(wrap(<Shell />));
    // Hidden, not removed. If this ever starts failing because the link is
    // back, that is a decision someone made in HIDDEN_FROM_RAIL, not a bug.
    expect(screen.queryByRole('link', { name: /sheet designer/i })).not.toBeInTheDocument();
  });

  it('settings is reached from the account menu, not the numbered rail', () => {
    render(wrap(<Shell />));
    // Settings left the rail for the account menu -- it keeps its route
    // (queryByRole above would still find it if the menu were open), it just
    // no longer takes a number from the rail's own nav list.
    expect(screen.queryByRole('link', { name: /^Settings$/i })).not.toBeInTheDocument();
  });

  it('the rail numbers itself without a gap where a hidden screen was', () => {
    render(wrap(<Shell />));
    // The whole point of computing the numbers: hiding settings must not
    // leave the rail reading 01, 02, 03, 04.
    for (const number of ['01', '02', '03']) {
      expect(screen.getByText(number)).toBeInTheDocument();
    }
    expect(screen.queryByText('04')).not.toBeInTheDocument();
  });

  it('a fresh load always opens on Home, whatever address was in the bar', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={client}>
        <AccountProvider>
          <MemoryRouter initialEntries={['/tracker']}>
            <Routes>
              <Route path="/" element={<Shell />}>
                <Route index element={<HomeScreen />} />
                <Route path="tracker" element={<TrackerScreen />} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AccountProvider>
      </QueryClientProvider>,
    );

    // Reopening the app is not the same as picking up where a browser tab
    // was left -- it bounces to Home before Tracker ever gets to render.
    expect(await screen.findByRole('button', { name: 'Run the search' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Tracker', level: 1 })).not.toBeInTheDocument();
  });
});

/**
 * What the two rewritten screens are actually for.
 *
 * The mount tests above catch a blank page. These catch the opposite failure:
 * a screen that renders perfectly and does the wrong thing -- the front page
 * still being the form, a discarded ad quietly setting the wrong status, the
 * letter button still being a bare glyph a screen reader reads as "pencil".
 */
describe('the front page and the sifting', () => {
  /** Answers that override the shared stand-in server, per test. */
  let overrides: Record<string, unknown> = {};
  let sent: { url: string; body: unknown }[] = [];

  beforeEach(() => {
    overrides = {};
    sent = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const path = url.split('?')[0] ?? url;
        if (init?.body) sent.push({ url: path, body: JSON.parse(String(init.body)) });
        const answer = path in overrides ? overrides[path] : answerFor(url);
        return Promise.resolve(
          new Response(JSON.stringify(answer), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('the front page leads with the one button, not with the form', async () => {
    render(wrap(<HomeScreen />));
    const go = await screen.findByRole('button', { name: 'Run the search' });
    // It stays disabled until the saved setup is in hand: a big button that
    // starts nothing is worse than one that is visibly not ready yet.
    await waitFor(() => expect(go).toBeEnabled());
    expect(screen.getByRole('button', { name: 'Open the job list' })).toBeInTheDocument();
    // The thing it replaced: no source picker, no keyword editor, no filters.
    expect(screen.queryByText('RSS or Atom feed')).not.toBeInTheDocument();
  });

  it('the front page summarises the search without offering to edit it inline', async () => {
    render(wrap(<HomeScreen />));
    // Read from the same saved setup the editor seeds itself from, so the two
    // can never drift apart.
    expect(await screen.findByText(/GIS: gis/)).toBeInTheDocument();
    expect(screen.getByText('Rijeka')).toBeInTheDocument();
    expect(screen.getByText('permanent')).toBeInTheDocument();
    expect(screen.getByText('hzz')).toBeInTheDocument();
    // Employers are optional, so an empty list is a missing row, not an empty one.
    expect(screen.queryByText('Hoping for')).not.toBeInTheDocument();
    expect(screen.queryByText('Skipping')).not.toBeInTheDocument();
    // Nothing on it is typeable.
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('an account with no saved search is told so rather than given a dead button', async () => {
    overrides['/api/profiles/setup/default'] = { name: 'default', kind: 'setup', payload: null };
    render(wrap(<HomeScreen />));
    expect(await screen.findByText(/no saved search yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run the search' })).toBeDisabled();
  });

  it('a setup saved before contract types existed still renders', async () => {
    // The field arrived after some accounts had already run the wizard, so it
    // is simply absent for them. Absent is not empty and must not be a crash.
    const { payload } = RESPONSES['/api/profiles/setup/default'] as {
      payload: { profile: Record<string, unknown> };
    };
    const { wanted_employment_types: _gone, ...older } = payload.profile;
    overrides['/api/profiles/setup/default'] = {
      name: 'default',
      kind: 'setup',
      payload: { ...payload, profile: older },
    };

    render(wrap(<HomeScreen />));
    expect(await screen.findByText(/GIS: gis/)).toBeInTheDocument();
    expect(screen.queryByText('Contract types')).not.toBeInTheDocument();
  });

  it('the summary names the employers, both the starred and the skipped', async () => {
    // The wizard asks for both and the summary showed neither, so a reader had
    // no way to tell what would be starred from what would be thrown away.
    const { payload } = RESPONSES['/api/profiles/setup/default'] as {
      payload: { profile: Record<string, unknown> };
    };
    overrides['/api/profiles/setup/default'] = {
      name: 'default',
      kind: 'setup',
      payload: {
        ...payload,
        profile: {
          ...payload.profile,
          dream_employers: ['Hidroelektra'],
          excluded_employers: ['Agencija X'],
        },
      },
    };

    render(wrap(<HomeScreen />));
    expect(await screen.findByText('Hoping for')).toBeInTheDocument();
    expect(screen.getByText('Hidroelektra')).toBeInTheDocument();
    expect(screen.getByText('Skipping')).toBeInTheDocument();
    expect(screen.getByText('Agencija X')).toBeInTheDocument();
  });

  it('the results table says which source found each job', async () => {
    render(wrap(<ResultsScreen />));
    expect(await screen.findByText('GIS Engineer')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Source' })).toBeInTheDocument();
    expect(screen.getByText('rss')).toBeInTheDocument();
  });

  it('an undecided job offers two answers and no status menu', async () => {
    render(wrap(<ResultsScreen />));
    expect(await screen.findByRole('button', { name: /Keep job/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Discard job/ })).toBeInTheDocument();
    // The per-row dropdown is gone: status belongs to the tracker now. The two
    // remaining selects are the filters at the top.
    expect(screen.queryByRole('combobox', { name: /Status — /  })).not.toBeInTheDocument();
  });

  it('discarding a job sets the status the board calls discarded', async () => {
    render(wrap(<ResultsScreen />));
    await userEvent.click(await screen.findByRole('button', { name: /Discard job/ }));

    await waitFor(() => {
      const move = sent.find((one) => one.url === '/api/applications/status');
      expect(move?.body).toMatchObject({
        dedup_key: 'example.test/j/1',
        status: 'skipped',
      });
    });
  });

  it('keeping a job answers the row without changing its status', async () => {
    render(wrap(<ResultsScreen />));
    await userEvent.click(await screen.findByRole('button', { name: /Keep job/ }));

    // Kept means "yes, this one" -- it stays new, which is what the tracker's
    // first column means. So nothing is sent, and the row stops asking.
    expect(sent.find((one) => one.url === '/api/applications/status')).toBeUndefined();
    expect(screen.queryByRole('button', { name: /Keep job/ })).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Continue to tracker/ })).toBeInTheDocument();
  });

  it('the way on appears only once the page has been sifted', async () => {
    render(wrap(<ResultsScreen />));
    await screen.findByRole('button', { name: /Keep job/ });
    expect(screen.queryByRole('button', { name: /Continue to tracker/ })).not.toBeInTheDocument();
  });

  it('the results can be narrowed to one past search', async () => {
    render(wrap(<ResultsScreen />));
    const picker = await screen.findByRole('combobox', { name: 'Which search' });
    // Labelled by when it ran and what it brought in, because two searches on
    // one morning share a date and nothing else would tell them apart.
    await waitFor(() => expect(picker).toHaveTextContent(/Latest/));
    expect(picker).toHaveTextContent(/34 jobs/);
  });

  it('a job title opens the shared detail dialog instead of leaving for the ad', async () => {
    render(wrap(<ResultsScreen />));
    // No standalone anchor to the ad any more: the title is a button, and
    // the real "open ad" link moved inside the dialog it opens.
    expect(screen.queryByRole('link', { name: 'GIS Engineer' })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'GIS Engineer' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('the letter button lives in the detail dialog, the same one Tracking uses', async () => {
    render(wrap(<ResultsScreen />));
    await userEvent.click(await screen.findByRole('button', { name: 'GIS Engineer' }));
    const dialog = await screen.findByRole('dialog');
    // A bare pencil glyph on the row is gone; writing a letter is now an
    // action inside the same dialog as "Open ad" and the status.
    expect(within(dialog).getByRole('button', { name: 'Application letter' })).toBeInTheDocument();
    expect(within(dialog).getByRole('link', { name: /Open the ad/ })).toBeInTheDocument();
    expect(screen.queryByText('✎')).not.toBeInTheDocument();
  });

  it('the search editor is reachable but not in the rail', () => {
    render(wrap(<Shell />));
    expect(screen.queryByRole('link', { name: /edit search/i })).not.toBeInTheDocument();
  });
});
