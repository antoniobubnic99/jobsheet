/**
 * Changing where the workbook lives.
 *
 * The failure worth testing is not the request. It is the checkbox: a person
 * who changes the path without moving the file keeps opening the workbook they
 * have always opened, sees nothing new in it, and has no way of knowing that
 * JobSheet has quietly started writing somewhere else. So the move is on by
 * default, and turning it off says out loud what that means.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import type { AppSettings } from '@/lib/types';
import WorkbookSection from '@/components/WorkbookSection';

const SETTINGS: AppSettings = {
  version: '0.1.0',
  python: '3.11.9',
  platform: 'Windows',
  home: 'C:\\JobSheet',
  workbook: 'C:\\JobSheet\\jobs.xlsx',
  workbook_exists: true,
  workbook_locked: false,
  database: 'C:\\JobSheet\\jobsheet.sqlite3',
  backups: 'C:\\JobSheet\\backups',
  keep_backups: 20,
  sources_installed: 14,
};

const FOLDERS = {
  path: 'C:\\JobSheet',
  parent: 'C:\\',
  home: 'C:\\Users\\ana',
  jobsheet_home: 'C:\\JobSheet',
  roots: [{ name: 'C:', path: 'C:\\' }],
  writable: true,
  folders: [{ name: 'backups', path: 'C:\\JobSheet\\backups' }],
  message: '',
};

const calls: { path: string; method: string; body: any }[] = [];

function serve(reply: { status?: number; body?: unknown } = {}) {
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
      if (path === '/api/settings/workbook') {
        return Promise.resolve(
          new Response(JSON.stringify(reply.body ?? { moved: true }), {
            status: reply.status ?? 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      const body = path === '/api/settings/folders' ? FOLDERS : {};
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
      <WorkbookSection settings={SETTINGS} />
    </QueryClientProvider>,
  );
}

const saved = () => calls.filter((call) => call.path === '/api/settings/workbook');

describe('the workbook path', () => {
  beforeEach(() => {
    void i18n.changeLanguage('en');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('shows where the workbook is before anybody asks to move it', () => {
    serve();
    mount();
    expect(screen.getByText('C:\\JobSheet\\jobs.xlsx')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
  });

  it('offers a folder to pick and a name to type, not a path to get right', async () => {
    serve();
    mount();
    await userEvent.click(screen.getByRole('button', { name: /Change where it is/ }));

    expect(await screen.findByRole('button', { name: 'backups' })).toBeInTheDocument();
    expect(screen.getByLabelText('File name')).toHaveValue('jobs.xlsx');
  });

  it('sends the folder and the name as one path, and takes the file along', async () => {
    serve();
    mount();
    await userEvent.click(screen.getByRole('button', { name: /Change where it is/ }));
    await screen.findByRole('button', { name: 'backups' });

    await userEvent.click(screen.getByRole('button', { name: 'backups' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(saved()).toHaveLength(1));
    expect(saved()[0]!.method).toBe('PUT');
    expect(saved()[0]!.body).toEqual({
      path: 'C:\\JobSheet\\backups\\jobs.xlsx',
      // On by default: this is the half that keeps a year of ticks.
      move: true,
    });
  });

  it('takes a new file name without touching the folder', async () => {
    serve();
    mount();
    await userEvent.click(screen.getByRole('button', { name: /Change where it is/ }));

    const name = screen.getByLabelText('File name');
    await userEvent.clear(name);
    await userEvent.type(name, 'poslovi.xlsx');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(saved()).toHaveLength(1));
    expect(saved()[0]!.body.path).toBe('C:\\JobSheet\\poslovi.xlsx');
  });

  it('survives a folder listing that arrives without a folder list', async () => {
    /** Found by the wizard's tests, where the stand-in server answers `{}` to
        anything it was not told about. The type promises a `folders` key; the
        wire does not, and reading `.length` off nothing took the page down. */
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
        ),
      ),
    );
    mount();

    await userEvent.click(screen.getByRole('button', { name: /Change where it is/ }));

    expect(await screen.findByLabelText('File name')).toBeInTheDocument();
  });

  it('says what happens to the old workbook when the move is turned off', async () => {
    serve();
    mount();
    await userEvent.click(screen.getByRole('button', { name: /Change where it is/ }));

    await userEvent.click(screen.getByRole('checkbox'));

    expect(screen.getByText(/stay in the old workbook/)).toBeInTheDocument();
  });

  it('leaves the move out of the request when it was turned off', async () => {
    serve({ body: { moved: false } });
    mount();
    await userEvent.click(screen.getByRole('button', { name: /Change where it is/ }));
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(saved()).toHaveLength(1));
    expect(saved()[0]!.body.move).toBe(false);
  });

  it('shows the server sentence when the workbook is open in Excel', async () => {
    /** The one refusal a person will actually hit, and the one they can fix. */
    serve({
      status: 409,
      body: { detail: { code: 'workbook_locked', message: 'jobs.xlsx is open in Excel.' } },
    });
    mount();
    await userEvent.click(screen.getByRole('button', { name: /Change where it is/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/open in Excel/);
  });
});
