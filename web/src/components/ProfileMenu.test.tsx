/**
 * The account, and the fact that it is reachable at all.
 *
 * The bug this covers is invisible to a render test and to a desktop browser:
 * the name and the sign-out were behind `hidden md:block`, so below 768px the
 * app would not say whose job search you were reading and gave you no way out
 * of it. Nothing threw, nothing looked broken, and one laptop can hold several
 * people's searches.
 *
 * jsdom has no viewport to shrink, so the test asserts the thing that made the
 * width matter: the name and every account action are in the document with no
 * media query standing between them and the reader.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import { AccountProvider } from '@/lib/account';
import Shell from '@/components/Shell';

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

const calls: { path: string; method: string }[] = [];

function serve() {
  calls.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).split('?')[0] ?? '';
      calls.push({ path, method: init?.method ?? 'GET' });
      const body = path === '/api/auth/me' ? ACCOUNT : {};
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
}

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AccountProvider>
        <MemoryRouter>
          <Shell />
        </MemoryRouter>
      </AccountProvider>
    </QueryClientProvider>,
  );
}

/** Open the menu and hand back the trigger, for tests that close it again. */
async function openMenu() {
  const trigger = await screen.findByRole('button', { expanded: false });
  await userEvent.click(trigger);
  await screen.findByRole('menu');
  return trigger;
}

describe('the profile menu', () => {
  beforeEach(() => {
    void i18n.changeLanguage('en');
    serve();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('says who is signed in without being asked', async () => {
    mount();
    expect(await screen.findByText('ana')).toBeInTheDocument();
  });

  it('leads to the one search this account has, and to the settings', async () => {
    mount();
    await openMenu();

    // Singular on purpose: one account, one search.
    const search = screen.getByRole('menuitem', { name: /My search/ });
    expect(search).toHaveAttribute('href', '/search/edit');
    expect(screen.getByRole('menuitem', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/settings',
    );
  });

  it('asks before signing out, and does not sign out until it is answered', async () => {
    mount();
    await openMenu();

    await userEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }));

    expect(screen.getByText(/Sign out\?/)).toBeInTheDocument();
    expect(calls.some((call) => call.path === '/api/auth/logout')).toBe(false);
  });

  it('signs out once the question is answered', async () => {
    mount();
    await openMenu();
    await userEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }));

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    await waitFor(() =>
      expect(calls.some((call) => call.path === '/api/auth/logout')).toBe(true),
    );
  });

  it('takes back the question when it is declined', async () => {
    mount();
    await openMenu();
    await userEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }));

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByText(/Sign out\?/)).not.toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toBeInTheDocument();
    expect(calls.some((call) => call.path === '/api/auth/logout')).toBe(false);
  });

  it('closes on Escape, so it cannot sit open over the screen behind it', async () => {
    mount();
    await openMenu();

    await userEvent.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('closes when the reader clicks past it', async () => {
    mount();
    await openMenu();

    await userEvent.click(screen.getByRole('link', { name: /Tracker/ }));

    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });
});

describe('the rail', () => {
  beforeEach(() => {
    void i18n.changeLanguage('en');
    serve();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('numbers the tracker 03, the same as its heading, and gives settings no rail slot', async () => {
    /** The rail and each screen's own heading print the same number now, so a
        hidden screen cannot leave the two disagreeing. Settings moved into the
        account menu, so it takes no number here at all. */
    mount();
    await screen.findByText('ana');

    expect(screen.getByText('03').closest('a')).toHaveAttribute('href', '/tracker');
    expect(screen.queryByText('04')).not.toBeInTheDocument();
    // The menu is closed at this point, so the only "Settings" this could
    // match is a rail link -- there must not be one.
    expect(screen.queryByRole('link', { name: 'Settings' })).not.toBeInTheDocument();
  });

  it('keeps the language switch reachable at every width', async () => {
    mount();
    await screen.findByText('ana');
    // It, too, used to be `hidden md:flex`.
    expect(screen.getByRole('button', { name: 'hr' })).toBeInTheDocument();
  });
});
