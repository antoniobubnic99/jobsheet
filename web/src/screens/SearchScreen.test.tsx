/**
 * Ticking a source used to hand it nothing but its own manifest defaults --
 * "Narodne novine" opened with an empty, required `terms` field even after
 * the user had already typed what they were looking for two sections up.
 * This covers the fix: a source ticked here starts from what the profile
 * already says, the same way "select all" starts every source from it at
 * once.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import type { ParamSpec, SourceManifest } from '@/lib/types';
import SearchScreen from '@/screens/SearchScreen';

function spec(overrides: Partial<ParamSpec>): ParamSpec {
  return {
    name: 'field',
    label: 'Field',
    kind: 'text',
    required: false,
    default: null,
    choices: [],
    placeholder: '',
    help: '',
    ...overrides,
  };
}

const NARODNE_NOVINE: SourceManifest = {
  id: 'narodne_novine',
  name: 'Narodne novine',
  homepage: '',
  description: '',
  country: 'HR',
  params: [
    spec({ name: 'terms', label: 'NN search words', required: true, default: null }),
    spec({ name: 'days', label: 'NN days back', kind: 'number', default: 30 }),
    spec({ name: 'max_pages', label: 'NN max pages', kind: 'number', default: 30 }),
  ],
  rate_limit: 1,
  supports_enrich: false,
  needs_credentials: false,
  is_global: false,
  health: null,
};

const SELEKCIJA: SourceManifest = {
  id: 'selekcija',
  name: 'Selekcija',
  homepage: '',
  description: '',
  country: 'HR',
  params: [spec({ name: 'days', label: 'Selekcija days back', kind: 'number', default: 45 })],
  rate_limit: 1,
  supports_enrich: false,
  needs_credentials: false,
  is_global: false,
  health: null,
};

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  );
}

function serve() {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const path = String(input).split('?')[0] ?? '';
      if (path === '/api/sources') {
        return json({ sources: [NARODNE_NOVINE, SELEKCIJA], countries: ['HR'] });
      }
      if (path === '/api/profiles/search') return json([]);
      // No wizard setup for this account: the seeding effect must stay out of
      // the way of a profile built by hand, in the test as in the app.
      if (path === '/api/profiles/setup/default') return json({ detail: 'not found' }, 404);
      if (path === '/api/places') return json({ places: [], counties: [] });
      return json({});
    }),
  );
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SearchScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** The label a ticked source's checkbox sits inside, by the source's name. */
function cardCheckbox(name: string) {
  const label = screen.getByText(name).closest('label');
  if (!label) throw new Error(`no card found for ${name}`);
  return within(label).getByRole('checkbox');
}

describe('the search screen', () => {
  beforeEach(() => {
    void i18n.changeLanguage('en');
    serve();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('fills a source from the profile the moment it is ticked', async () => {
    mount();
    await screen.findByText('Narodne novine');

    await userEvent.click(screen.getByRole('button', { name: '+ Add a category' }));
    await userEvent.type(screen.getByLabelText('Words that mean it 1'), 'geodetski{Enter}');

    fireEvent.change(screen.getByLabelText(/Ignore ads older than/), { target: { value: '14' } });

    await userEvent.click(cardCheckbox('Narodne novine'));

    expect(screen.getByLabelText(/NN search words/)).toHaveValue('geodetski');
    expect(screen.getByLabelText('NN days back')).toHaveValue(14);
    // Untouched by the profile, so it keeps its own manifest default.
    expect(screen.getByLabelText('NN max pages')).toHaveValue(30);
  });

  it('fills every source at once through "select all"', async () => {
    mount();
    await screen.findByText('Narodne novine');

    await userEvent.click(screen.getByRole('button', { name: '+ Add a category' }));
    await userEvent.type(screen.getByLabelText('Words that mean it 1'), 'katastar{Enter}');

    fireEvent.change(screen.getByLabelText(/Ignore ads older than/), { target: { value: '21' } });

    await userEvent.click(screen.getByRole('button', { name: 'Select all' }));

    expect(screen.getByLabelText(/NN search words/)).toHaveValue('katastar');
    expect(screen.getByLabelText('NN days back')).toHaveValue(21);
    expect(screen.getByLabelText('Selekcija days back')).toHaveValue(21);
    expect(screen.getByText('2 sources chosen')).toBeInTheDocument();
  });

  it('leaves an already-ticked source alone rather than overwriting a manual edit', async () => {
    mount();
    await screen.findByText('Narodne novine');

    await userEvent.click(cardCheckbox('Selekcija'));
    fireEvent.change(screen.getByLabelText('Selekcija days back'), { target: { value: '7' } });
    expect(screen.getByLabelText('Selekcija days back')).toHaveValue(7);

    // Ticking Narodne novine afterwards must not touch Selekcija's field --
    // "select all" only fills in sources that were not already chosen.
    await userEvent.click(screen.getByRole('button', { name: 'Select all' }));

    expect(screen.getByLabelText('Selekcija days back')).toHaveValue(7);
  });
});
