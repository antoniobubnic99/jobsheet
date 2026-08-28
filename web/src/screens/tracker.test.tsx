/**
 * The board, tested for the three things a person does to a card.
 *
 * All three failed in a way a render test cannot see. The card could only be
 * dragged by a handle the width of a fingernail; details opened only from the
 * title; and moving a card between columns on a phone was, in practice,
 * impossible -- the board scrolls sideways, so the target column is off the
 * screen while you are holding the card.
 *
 * The other thing tested here is that the column order comes from the server.
 * It used to come from a constant in this file's subject as well, which is two
 * places for one fact.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import { AccountProvider } from '@/lib/account';
import TrackerScreen from './TrackerScreen';

const BOARD_ORDER = ['skipped', 'new', 'applied', 'interview', 'offer', 'rejected'] as const;

function row(number: number, status: string) {
  return {
    dedup_key: `example.test/j/${number}`,
    posting: {
      source_id: 'rss',
      title: `GIS Engineer ${number}`,
      url: `https://example.test/j/${number}`,
      company: 'Kartograf d.o.o.',
      location: 'Rijeka',
      region: '',
      workplace: 'onsite',
      description: '',
      employment_type: '',
      education: '',
      salary: '',
      posted_at: '2026-08-01',
      deadline: null,
      tags: [],
    },
    found_at: '2026-08-24',
    category: 'GIS',
    note: '',
    status,
    user_values: {},
    link_text: '',
  };
}

function board(placed: Record<string, number[]>, order: readonly string[] = BOARD_ORDER) {
  const columns = Object.fromEntries(
    order.map((status) => [status, (placed[status] ?? []).map((n) => row(n, status))]),
  );
  return {
    order: [...order],
    counts: Object.fromEntries(order.map((status) => [status, columns[status]!.length])),
    columns,
  };
}

const calls: { path: string; method: string; body: unknown }[] = [];

function serve(reply: unknown) {
  calls.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).split('?')[0] ?? '';
      calls.push({
        path,
        method: init?.method ?? 'GET',
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      const body = path === '/api/applications/board' ? reply : path.endsWith('/history') ? [] : {};
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
          <TrackerScreen />
        </MemoryRouter>
      </AccountProvider>
    </QueryClientProvider>,
  );
}

const moves = () => calls.filter((call) => call.path === '/api/applications/status');

describe('the board', () => {
  beforeEach(() => {
    void i18n.changeLanguage('en');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('draws the columns in the order the server sent, not its own', async () => {
    // Deliberately backwards. If the constant were still in charge this would
    // come back the other way round and nobody would ever notice in the app.
    const backwards = ['rejected', 'offer', 'interview', 'applied', 'new', 'skipped'] as const;
    serve(board({ new: [1] }, backwards));
    const { container } = mount();
    await screen.findByText('GIS Engineer 1');

    const headers = [...container.querySelectorAll('section > header')].map(
      (header) => header.textContent ?? '',
    );
    expect(headers[0]).toContain('Rejected');
    expect(headers.at(-1)).toContain('Discarded');
  });

  it('calls the first column Discarded, and still calls Rejected Rejected', async () => {
    /** Two different stories: I said no, and they said no. */
    serve(board({ skipped: [1], rejected: [2] }));
    const { container } = mount();
    await screen.findByText('GIS Engineer 1');

    const headers = [...container.querySelectorAll('section > header')].map(
      (header) => header.textContent ?? '',
    );
    expect(headers[0]).toContain('Discarded');
    expect(headers.at(-1)).toContain('Rejected');
  });

  it('opens the details from anywhere on the card, not only the title', async () => {
    serve(board({ new: [1] }));
    mount();
    await screen.findByText('GIS Engineer 1');

    // The company line: previously dead space on a card you could only open by
    // hitting the title exactly.
    await userEvent.click(screen.getByText(/Kartograf/));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('puts the whole decision in the dialog: status, the ad, a letter, discard', async () => {
    serve(board({ new: [1] }));
    mount();
    await screen.findByText('GIS Engineer 1');
    await userEvent.click(screen.getByText(/Kartograf/));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('link', { name: /Open the ad/ })).toBeInTheDocument();
    // By key, not by wording: the letter button's label belongs to the results
    // screen and is not this test's to pin down.
    expect(
      within(dialog).getByRole('button', { name: i18n.t('results.letter') }),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Discard' })).toBeInTheDocument();
    expect(within(dialog).getByRole('combobox')).toHaveValue('new');
  });

  it('discards from the dialog without asking the user to find the column', async () => {
    serve(board({ new: [1] }));
    mount();
    await screen.findByText('GIS Engineer 1');
    await userEvent.click(screen.getByText(/Kartograf/));

    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Discard' }));

    await waitFor(() => expect(moves()).toHaveLength(1));
    expect(moves()[0]!.body).toMatchObject({
      dedup_key: 'example.test/j/1',
      status: 'skipped',
    });
  });

  it('offers no discard on a card that is already discarded', async () => {
    serve(board({ skipped: [1] }));
    mount();
    await screen.findByText('GIS Engineer 1');
    await userEvent.click(screen.getByText(/Kartograf/));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByRole('button', { name: 'Discard' })).not.toBeInTheDocument();
  });

  it('moves the top card one column along with the arrow above it', async () => {
    /** The only workable gesture on a phone: the board scrolls sideways, so the
        column you are aiming at is off the screen while you hold the card. */
    serve(board({ new: [1] }));
    mount();
    await screen.findByText('GIS Engineer 1');

    await userEvent.click(
      screen.getByRole('button', { name: 'Move GIS Engineer 1 to Applied' }),
    );

    await waitFor(() => expect(moves()).toHaveLength(1));
    expect(moves()[0]!.body).toMatchObject({
      dedup_key: 'example.test/j/1',
      status: 'applied',
    });
  });

  it('sends the top card the other way too', async () => {
    serve(board({ applied: [1] }));
    mount();
    await screen.findByText('GIS Engineer 1');

    await userEvent.click(screen.getByRole('button', { name: 'Move GIS Engineer 1 to New' }));

    await waitFor(() => expect(moves()).toHaveLength(1));
    expect(moves()[0]!.body).toMatchObject({ status: 'new' });
  });

  it('has no live arrow over an empty column or at the end of the board', async () => {
    serve(board({ new: [1] }));
    const { container } = mount();
    await screen.findByText('GIS Engineer 1');

    const dead = screen.getAllByRole('button', { name: 'Nothing to move' });
    // Every column but `new` is empty, and both ends have one arrow into space.
    expect(dead.length).toBeGreaterThan(0);
    expect(dead.every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
    expect(container.querySelectorAll('section > header')).toHaveLength(6);
  });

  it('keeps the select on the card, because it is the only keyboard route', async () => {
    serve(board({ new: [1] }));
    mount();
    await screen.findByText('GIS Engineer 1');

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: /Status — GIS Engineer 1/ }),
      'interview',
    );

    await waitFor(() => expect(moves()).toHaveLength(1));
    expect(moves()[0]!.body).toMatchObject({ status: 'interview' });
  });

  it('does not open the details when the select on a card is used', async () => {
    /** Both live on the same surface now; the select has to keep its click. */
    serve(board({ new: [1] }));
    mount();
    await screen.findByText('GIS Engineer 1');

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: /Status — GIS Engineer 1/ }),
      'offer',
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('says something about the tracker when the board is empty', async () => {
    serve(board({}));
    mount();

    // Not the results screen's "run a search and they will land here": this is
    // a different screen answering for itself.
    expect(await screen.findByText(/Nothing to track yet/)).toBeInTheDocument();
  });
});
