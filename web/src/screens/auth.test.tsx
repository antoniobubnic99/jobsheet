/**
 * The door and the hallway.
 *
 * `Gate` is three lines of logic guarding every screen in the app, which makes
 * it the single place where a mistake is worst: too strict and nobody gets in,
 * too loose and a signed-out browser sees somebody's job search. So each of its
 * three answers is tested against a server that gives the matching reply.
 *
 * The wizard is tested for the one thing it promises -- that finishing produces
 * a search which can actually run -- and for the one thing it refuses.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import { AccountProvider } from '@/lib/account';
import Gate from '@/components/Gate';

const ACCOUNT = {
  id: 1,
  username: 'ana',
  onboarded: true,
  has_password: true,
  workbook: null,
  created_at: '2026-08-24T09:00:00',
  workbook_path: 'C:/JobSheet/jobs.xlsx',
  home: 'C:/JobSheet',
  primary: true,
};

const SOURCES = {
  countries: ['HR'],
  sources: [
    {
      id: 'hzz',
      name: 'HZZ Burza rada',
      homepage: 'https://burzarada.hzz.hr/',
      description: 'Croatian public employment service.',
      country: 'HR',
      params: [],
      rate_limit: 0.7,
      supports_enrich: true,
      needs_credentials: false,
      is_global: false,
      health: null,
    },
  ],
};

interface Reply {
  status?: number;
  body?: unknown;
}

/** A stand-in JobSheet. Unlisted paths answer `{}` with a 200, as most do. */
function serve(replies: Record<string, Reply>) {
  const calls: { path: string; method: string; body: unknown }[] = [];

  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).split('?')[0] ?? '';
      calls.push({
        path,
        method: init?.method ?? 'GET',
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      const reply = replies[`${init?.method ?? 'GET'} ${path}`] ?? replies[path] ?? {};
      return Promise.resolve(
        new Response(JSON.stringify(reply.body ?? {}), {
          status: reply.status ?? 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );

  return calls;
}

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AccountProvider>
        <MemoryRouter>
          <Gate />
        </MemoryRouter>
      </AccountProvider>
    </QueryClientProvider>,
  );
}

const SIGNED_OUT: Reply = { status: 401, body: { detail: 'Sign in to JobSheet to use this.' } };

beforeEach(async () => {
  await i18n.changeLanguage('en');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the gate', () => {
  it('shows the door to a browser that is not signed in', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 1, claimable: null } },
    });
    mount();

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });

  it('shows the wizard to an account that has not been through it', async () => {
    serve({
      '/api/auth/me': { body: { ...ACCOUNT, onboarded: false } },
      '/api/sources': { body: SOURCES },
    });
    mount();

    expect(
      await screen.findByRole('heading', { name: 'What job are you after?' }),
    ).toBeInTheDocument();
  });

  it('shows the app to an account that has', async () => {
    serve({ '/api/auth/me': { body: ACCOUNT }, '/api/sources': { body: SOURCES } });
    mount();

    expect(await screen.findByRole('navigation')).toBeInTheDocument();
    expect(screen.getByText('ana')).toBeInTheDocument();
  });

  it('does not treat being signed out as an error', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 1, claimable: null } },
    });
    mount();

    await screen.findByRole('heading', { name: 'Sign in' });
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });
});

describe('the door', () => {
  it('offers to make an account when there are none', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 0, claimable: null } },
    });
    mount();

    expect(await screen.findByRole('heading', { name: 'Make your account' })).toBeInTheDocument();
    // Nothing to sign into, so nothing offers to.
    expect(screen.queryByText('I already have an account')).not.toBeInTheDocument();
  });

  it('offers the waiting search when an install predates accounts', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': {
        body: { accounts: 1, claimable: { ...ACCOUNT, username: 'local', has_password: false } },
      },
    });
    mount();

    expect(
      await screen.findByRole('heading', { name: 'This search is waiting for you' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Start fresh instead')).toBeInTheDocument();
  });

  it('translates a failure the server gave a code for', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 1, claimable: null } },
      'POST /api/auth/login': {
        status: 401,
        body: { detail: { code: 'bad_credentials', message: 'server wording' } },
      },
    });
    mount();
    await screen.findByRole('heading', { name: 'Sign in' });

    await userEvent.type(screen.getByLabelText('Username'), 'ana');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-one');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'That username and password do not match.',
    );
  });

  it('falls back to the server sentence for a code it has never heard of', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 1, claimable: null } },
      'POST /api/auth/login': {
        status: 422,
        body: { detail: { code: 'something_new', message: 'A brand new problem.' } },
      },
    });
    mount();
    await screen.findByRole('heading', { name: 'Sign in' });

    await userEvent.type(screen.getByLabelText('Username'), 'ana');
    await userEvent.type(screen.getByLabelText('Password'), 'whatever-it-is');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('A brand new problem.');
  });

  it('signing in swaps the door for the app', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 1, claimable: null } },
      'POST /api/auth/login': { body: ACCOUNT },
      '/api/sources': { body: SOURCES },
    });
    mount();
    await screen.findByRole('heading', { name: 'Sign in' });

    await userEvent.type(screen.getByLabelText('Username'), 'ana');
    await userEvent.type(screen.getByLabelText('Password'), 'a-good-password');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('navigation')).toBeInTheDocument();
  });
});

describe('the wizard', () => {
  const walkToTheEnd = async () => {
    for (let step = 0; step < 7; step += 1) {
      await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    }
  };

  it('will not finish without somewhere to look', async () => {
    serve({
      '/api/auth/me': { body: { ...ACCOUNT, onboarded: false } },
      '/api/sources': { body: SOURCES },
    });
    mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });

    await walkToTheEnd();

    expect(screen.getByRole('button', { name: 'Take me to the search' })).toBeDisabled();
    expect(
      screen.getByText('Pick at least one source. A search with nowhere to look finds nothing.'),
    ).toBeInTheDocument();
  });

  it('sends what it collected and hands over to the app', async () => {
    const calls = serve({
      '/api/auth/me': { body: { ...ACCOUNT, onboarded: false } },
      '/api/sources': { body: SOURCES },
      'POST /api/auth/onboarding': { body: ACCOUNT },
      '/api/profiles/setup/default': { status: 404, body: { detail: 'no such profile' } },
    });
    mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });

    await userEvent.type(screen.getByLabelText(/The job you want/), 'Surveyor');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    // 02 — one empty group is waiting, so the question is a field, not a button.
    await userEvent.type(screen.getByLabelText(/Category name/i), 'GIS');
    await userEvent.type(screen.getByLabelText(/Words that mean it/i), 'gis{Enter}');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    await userEvent.type(screen.getByLabelText(/Towns and cities/), 'Rijeka{Enter}');
    for (let step = 0; step < 4; step += 1) {
      await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    }

    // 07 — sources.
    await userEvent.click(screen.getByLabelText(/HZZ Burza rada/i));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    const finish = screen.getByRole('button', { name: 'Take me to the search' });
    await waitFor(() => expect(finish).toBeEnabled());
    await userEvent.click(finish);

    const sent = calls.find((call) => call.path === '/api/auth/onboarding');
    expect(sent).toBeDefined();
    const body = sent!.body as {
      setup: {
        headline: string;
        profile: { keyword_groups: { name: string; terms: string[] }[]; locations: string[] };
        sources: { source_id: string }[];
      };
    };
    expect(body.setup.headline).toBe('Surveyor');
    expect(body.setup.profile.keyword_groups).toEqual([{ name: 'GIS', terms: ['gis'] }]);
    expect(body.setup.profile.locations).toEqual(['Rijeka']);
    expect(body.setup.sources.map((one) => one.source_id)).toEqual(['hzz']);

    expect(await screen.findByRole('navigation')).toBeInTheDocument();
  });

  it('drops a half-typed keyword group rather than saving it', async () => {
    const calls = serve({
      '/api/auth/me': { body: { ...ACCOUNT, onboarded: false } },
      '/api/sources': { body: SOURCES },
      'POST /api/auth/onboarding': { body: ACCOUNT },
    });
    mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    // A name and no words: matches nothing, and would put an empty category in
    // the spreadsheet if it were kept.
    await userEvent.type(screen.getByLabelText(/Category name/i), 'GIS');

    for (let step = 0; step < 5; step += 1) {
      await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    }
    await userEvent.click(screen.getByLabelText(/HZZ Burza rada/i));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Take me to the search' }));

    const sent = calls.find((call) => call.path === '/api/auth/onboarding');
    const body = sent!.body as { setup: { profile: { keyword_groups: unknown[] } } };
    expect(body.setup.profile.keyword_groups).toEqual([]);
  });
});
