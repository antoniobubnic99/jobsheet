/**
 * The front page, the door and the hallway.
 *
 * `Gate` is three lines of logic guarding every screen in the app, which makes
 * it the single place where a mistake is worst: too strict and nobody gets in,
 * too loose and a signed-out browser sees somebody's job search. So each of its
 * three answers is tested against a server that gives the matching reply.
 *
 * The front page is tested for the two things it can get wrong in a way nobody
 * would notice: offering a sign-in on an install with no accounts, and opening
 * a different form from the one its button promised.
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
      // The real HZZ declares this, and declares it required: a source ticked
      // without its defaults fails the search on a missing parameter.
      params: [
        {
          name: 'counties',
          label: 'Counties',
          kind: 'multiselect',
          required: true,
          default: ['4'],
          choices: [{ value: '4', label: 'Grad Zagreb' }],
          placeholder: '',
          help: '',
        },
      ],
      rate_limit: 0.7,
      supports_enrich: true,
      needs_credentials: false,
      is_global: false,
      health: null,
    },
  ],
};

/** What the last step's folder picker gets. Unlisted paths answer `{}`, which it
 *  cannot render -- and a wizard that crashes on its own last screen is the one
 *  failure this file exists to catch. */
const FOLDERS = {
  path: 'C:/JobSheet',
  parent: 'C:/',
  home: 'C:/Users/ana',
  jobsheet_home: 'C:/JobSheet',
  roots: [{ name: 'C:', path: 'C:/' }],
  writable: true,
  folders: [{ name: 'Documents', path: 'C:/JobSheet/Documents' }],
  message: '',
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

/** What the door tells a visitor. `sources` is what the front page promises. */
const DOOR = { count: 2, names: ['HZZ Burza rada', 'Remotive'] };

/**
 * The front page comes first now, so most of these tests start by leaving it.
 *
 * The first match, deliberately: the front page offers its main action twice,
 * at the top and at the bottom, which is what a page you scroll should do.
 */
async function step(name: string | RegExp) {
  const buttons = await screen.findAllByRole('button', { name });
  await userEvent.click(buttons[0]!);
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
  // The wizard now keeps a draft, which is the whole point of it -- and which
  // would otherwise carry one test's answers into the next.
  sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the gate', () => {
  it('shows the front page to a browser that is not signed in', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 1, claimable: null, sources: DOOR } },
    });
    mount();

    expect(
      await screen.findByRole('heading', { name: /one spreadsheet you own/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    // The form is behind a click, not on the page.
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
  });

  it('shows the wizard to an account that has not been through it', async () => {
    serve({
      '/api/auth/me': { body: { ...ACCOUNT, onboarded: false } },
      '/api/sources': { body: SOURCES },
      '/api/settings/folders': { body: FOLDERS },
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
      '/api/auth/status': { body: { accounts: 1, claimable: null, sources: DOOR } },
    });
    mount();

    await screen.findByRole('heading', { name: /one spreadsheet you own/i });
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });
});

describe('the front page', () => {
  const signedOut = (extra: Record<string, Reply> = {}) =>
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 1, claimable: null, sources: DOOR } },
      ...extra,
    });

  it('names the sources this install actually has', async () => {
    signedOut();
    mount();

    expect(await screen.findByText('2 sources')).toBeInTheDocument();
    expect(screen.getByText('HZZ Burza rada')).toBeInTheDocument();
    expect(screen.getByText('Remotive')).toBeInTheDocument();
  });

  it('promises no sources when the door could not say', async () => {
    // A page that invented a number here would be lying on the one screen
    // whose whole job is to be believed.
    signedOut({ '/api/auth/status': { status: 500, body: { detail: 'no' } } });
    mount();

    expect(
      await screen.findByText('The list is on the sources screen, once you are inside.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/sources$/)).not.toBeInTheDocument();
  });

  it('opens the form its button promised, not the other one', async () => {
    signedOut();
    mount();

    await step('Find a job');
    expect(await screen.findByRole('heading', { name: 'Make your account' })).toBeInTheDocument();
  });

  it('comes back when the form is left', async () => {
    signedOut();
    mount();

    await step('Sign in');
    await screen.findByRole('heading', { name: 'Sign in' });

    await step('Back');
    expect(
      await screen.findByRole('heading', { name: /one spreadsheet you own/i }),
    ).toBeInTheDocument();
  });
});

describe('the door', () => {
  it('offers to make an account when there are none', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 0, claimable: null, sources: DOOR } },
    });
    mount();

    // Nothing to sign into, so the front page does not offer it...
    await screen.findAllByRole('button', { name: 'Find a job' });
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument();

    await step('Find a job');
    expect(await screen.findByRole('heading', { name: 'Make your account' })).toBeInTheDocument();
    // ...and neither does the form it opened.
    expect(screen.queryByText('I already have an account')).not.toBeInTheDocument();
  });

  it('offers the waiting search when an install predates accounts', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': {
        body: {
          accounts: 1,
          claimable: { ...ACCOUNT, username: 'local', has_password: false },
          sources: DOOR,
        },
      },
    });
    mount();

    // The front page says so in its own words before the form repeats it.
    await step('Take over the search that is here');
    expect(
      await screen.findByRole('heading', { name: 'This search is waiting for you' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Start fresh instead')).toBeInTheDocument();
  });

  it('translates a failure the server gave a code for', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 1, claimable: null, sources: DOOR } },
      'POST /api/auth/login': {
        status: 401,
        body: { detail: { code: 'bad_credentials', message: 'server wording' } },
      },
    });
    mount();
    await step('Sign in');
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
      '/api/auth/status': { body: { accounts: 1, claimable: null, sources: DOOR } },
      'POST /api/auth/login': {
        status: 422,
        body: { detail: { code: 'something_new', message: 'A brand new problem.' } },
      },
    });
    mount();
    await step('Sign in');
    await screen.findByRole('heading', { name: 'Sign in' });

    await userEvent.type(screen.getByLabelText('Username'), 'ana');
    await userEvent.type(screen.getByLabelText('Password'), 'whatever-it-is');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('A brand new problem.');
  });

  it('signing in swaps the door for the app', async () => {
    serve({
      '/api/auth/me': SIGNED_OUT,
      '/api/auth/status': { body: { accounts: 1, claimable: null, sources: DOOR } },
      'POST /api/auth/login': { body: ACCOUNT },
      '/api/sources': { body: SOURCES },
    });
    mount();
    await step('Sign in');
    await screen.findByRole('heading', { name: 'Sign in' });

    await userEvent.type(screen.getByLabelText('Username'), 'ana');
    await userEvent.type(screen.getByLabelText('Password'), 'a-good-password');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('navigation')).toBeInTheDocument();
  });
});

describe('the wizard', () => {
  const walkToTheEnd = async () => {
    for (let step = 0; step < 6; step += 1) {
      await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    }
  };

  it('will not finish without somewhere to look', async () => {
    serve({
      '/api/auth/me': { body: { ...ACCOUNT, onboarded: false } },
      '/api/sources': { body: SOURCES },
      '/api/settings/folders': { body: FOLDERS },
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
      '/api/settings/folders': { body: FOLDERS },
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
    for (let step = 0; step < 3; step += 1) {
      await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    }

    // 06 — sources.
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
      '/api/settings/folders': { body: FOLDERS },
      'POST /api/auth/onboarding': { body: ACCOUNT },
    });
    mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    // A name and no words: matches nothing, and would put an empty category in
    // the spreadsheet if it were kept.
    await userEvent.type(screen.getByLabelText(/Category name/i), 'GIS');

    for (let step = 0; step < 4; step += 1) {
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

/**
 * The fields the wizard is made of, tested where they were complained about.
 *
 * Each of these was a real report: text that vanished, a chip that disappeared
 * under one keystroke, four screens of typing lost to a remount, and a step
 * nobody could tell what to do with.
 */
describe('the wizard fields', () => {
  const onboarding = (extra: Record<string, Reply> = {}) =>
    serve({
      '/api/auth/me': { body: { ...ACCOUNT, onboarded: false } },
      '/api/sources': { body: SOURCES },
      '/api/settings/folders': { body: FOLDERS },
      '/api/places': { body: { places: [], counties: [] } },
      '/api/postings/companies': { body: { companies: [], total: 0 } },
      ...extra,
    });

  const startAtKeywords = async () => {
    mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });
    await userEvent.type(screen.getByLabelText(/The job you want/), 'Surveyor');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  };

  const forward = async (times: number) => {
    for (let step = 0; step < times; step += 1) {
      await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    }
  };

  it('keeps a duplicate in the field instead of swallowing it', async () => {
    // The complaint, in the user's words: "when I click around, my typing gets
    // deleted". It was a duplicate being cleared without a word said.
    onboarding();
    await startAtKeywords();

    const words = screen.getByLabelText(/Words that mean it/i);
    await userEvent.type(words, 'gis{Enter}');
    await userEvent.type(words, 'gis');
    await userEvent.tab();

    expect(words).toHaveValue('gis');
    expect(await screen.findByRole('status')).toHaveTextContent('already in the list');
  });

  it('takes two backspaces to remove a chip, not one', async () => {
    onboarding();
    await startAtKeywords();

    const words = screen.getByLabelText(/Words that mean it/i);
    await userEvent.type(words, 'gis{Enter}');

    // `keyboard` rather than `type`, which clicks first: a click in the field
    // disarms, which is the behaviour, and would hide the thing being tested.
    await userEvent.keyboard('{Backspace}');
    expect(screen.getByRole('status')).toHaveTextContent('Backspace again');
    expect(screen.getByText('gis')).toBeInTheDocument();

    await userEvent.keyboard('{Backspace}');
    expect(screen.queryByText('gis')).not.toBeInTheDocument();

    // And a click between the two presses puts the chip back out of reach.
    await userEvent.type(words, 'cad{Enter}');
    await userEvent.keyboard('{Backspace}');
    await userEvent.click(words);
    await userEvent.keyboard('{Backspace}');
    expect(screen.getByText('cad')).toBeInTheDocument();
  });

  it('says what the keywords step is going to do', async () => {
    onboarding();
    await startAtKeywords();

    // The explanation of stems is the answer to "I do not understand this screen".
    expect(screen.getByText(/beginnings, not whole words/)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Category name/i), 'GIS');
    await userEvent.type(screen.getByLabelText(/Words that mean it/i), 'gis{Enter}');

    expect(screen.getByText(/under the category/)).toBeInTheDocument();
  });

  it('warns about having no keywords without blocking the way forward', async () => {
    onboarding();
    await startAtKeywords();

    expect(
      screen.getByText(/every ad from every source you pick comes through/),
    ).toBeInTheDocument();
    // Warned, never blocked: "show me the whole feed" is a legitimate request.
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
  });

  it('offers words from the headline, and only when asked', async () => {
    onboarding();
    await startAtKeywords();

    expect(screen.getByText(/From/)).toBeInTheDocument();
    // Nothing has been written into the field: it is an offer, not an autofill.
    expect(screen.getByLabelText(/Category name/i)).toHaveValue('');

    await userEvent.click(screen.getByRole('button', { name: 'Use these' }));
    expect(screen.getByLabelText(/Category name/i)).toHaveValue('Surveyor');
    expect(screen.getByText('surveyor')).toBeInTheDocument();
  });

  it('survives being unmounted with two screens of typing in it', async () => {
    // `Gate` swaps this component out whenever /api/auth/me answers 401 or the
    // server pauses long enough to look as though it has. Before the draft,
    // that threw the whole wizard away with nothing said and nothing to click.
    onboarding();
    const first = mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });
    await userEvent.type(screen.getByLabelText(/The job you want/), 'Surveyor');
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.type(screen.getByLabelText(/Category name/i), 'GIS');

    first.unmount();
    mount();

    expect(await screen.findByLabelText(/Category name/i)).toHaveValue('GIS');
    await userEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByLabelText(/The job you want/)).toHaveValue('Surveyor');
  });

  it('does not hand one account the half-finished wizard of another', async () => {
    onboarding();
    const first = mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });
    await userEvent.type(screen.getByLabelText(/The job you want/), 'Surveyor');
    first.unmount();

    serve({
      '/api/auth/me': { body: { ...ACCOUNT, id: 2, username: 'ivo', onboarded: false } },
      '/api/sources': { body: SOURCES },
      '/api/settings/folders': { body: FOLDERS },
    });
    mount();

    expect(await screen.findByLabelText(/The job you want/)).toHaveValue('');
  });

  it('picks every source at once, with the parameters each one needs', async () => {
    // The trap the bulk buttons had to be built around: HZZ declares `counties`
    // as required, so a source ticked without its defaults fails the search on
    // a missing parameter -- and does it later, on another screen.
    const calls = onboarding({ 'POST /api/auth/onboarding': { body: ACCOUNT } });
    mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });

    await forward(5);
    await userEvent.click(screen.getByRole('button', { name: 'Select all' }));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Take me to the search' }));

    const sent = calls.find((call) => call.path === '/api/auth/onboarding');
    const body = sent!.body as {
      setup: { sources: { source_id: string; params: Record<string, unknown> }[] };
    };
    expect(body.setup.sources.map((one) => one.source_id)).toEqual(['hzz']);
    expect(body.setup.sources[0]!.params).toEqual({ counties: ['4'] });
  });

  it('clears every source with one button', async () => {
    onboarding();
    mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });

    await forward(5);
    await userEvent.click(screen.getByRole('button', { name: 'Select all' }));
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('button', { name: 'Take me to the search' })).toBeDisabled();
  });

  it('sends the contracts that were ticked, and leaves the old field alone', async () => {
    const calls = onboarding({ 'POST /api/auth/onboarding': { body: ACCOUNT } });
    mount();
    await screen.findByRole('heading', { name: 'What job are you after?' });

    await forward(4);
    await userEvent.click(screen.getByLabelText(/Permanent/));
    // The fail-open rule, said out loud the moment a box is ticked.
    expect(screen.getByText(/still comes through, marked/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByLabelText(/HZZ Burza rada/i));
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await userEvent.click(screen.getByRole('button', { name: 'Take me to the search' }));

    const sent = calls.find((call) => call.path === '/api/auth/onboarding');
    const body = sent!.body as {
      setup: {
        profile: { wanted_employment_types: string[]; excluded_employment_types: string[] };
      };
    };
    expect(body.setup.profile.wanted_employment_types).toEqual(['neodređeno']);
    // A5's whole point: the old field is untouched, not renamed.
    expect(body.setup.profile.excluded_employment_types).toEqual([]);
  });
});
