/**
 * The three buttons that used to exist only inside the wizard's `StepSources`
 * -- this test is what moved with them into their own component, so both the
 * wizard and the "edit search" screen stay covered by one suite.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/i18n';
import type { SourceManifest } from '@/lib/types';
import SourceBulkActions from '@/components/SourceBulkActions';

function source(id: string, country: string | null): SourceManifest {
  return {
    id,
    name: id,
    homepage: '',
    description: '',
    country,
    params: [],
    rate_limit: 1,
    supports_enrich: false,
    needs_credentials: false,
    is_global: country === null,
    health: null,
  };
}

const SOURCES = [source('hzz', 'HR'), source('greenhouse', null), source('nn', 'HR')];

describe('the source bulk actions', () => {
  beforeEach(() => {
    void i18n.changeLanguage('en');
  });

  it('chooses every source at once', async () => {
    const onChoose = vi.fn();
    render(
      <SourceBulkActions sources={SOURCES} countries={['HR']} chosenCount={0} onChoose={onChoose} />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Select all' }));

    expect(onChoose).toHaveBeenCalledWith(SOURCES);
  });

  it('chooses only the sources from one country', async () => {
    const onChoose = vi.fn();
    render(
      <SourceBulkActions sources={SOURCES} countries={['HR']} chosenCount={0} onChoose={onChoose} />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Only HR' }));

    expect(onChoose).toHaveBeenCalledWith([SOURCES[0], SOURCES[2]]);
  });

  it('clears the choice', async () => {
    const onChoose = vi.fn();
    render(
      <SourceBulkActions sources={SOURCES} countries={['HR']} chosenCount={2} onChoose={onChoose} />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));

    expect(onChoose).toHaveBeenCalledWith([]);
  });

  it('reports how many are chosen', () => {
    render(
      <SourceBulkActions sources={SOURCES} countries={['HR']} chosenCount={2} onChoose={vi.fn()} />,
    );

    expect(screen.getByText('2 sources chosen')).toBeInTheDocument();
  });
});
