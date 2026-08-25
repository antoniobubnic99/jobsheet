/**
 * The language switch.
 *
 * The test that matters most is the boring one: that neither language has a
 * hole in it. A missing key falls back to English silently, which is exactly
 * the kind of half-translated interface that looks careless and is never
 * noticed by whoever added the key.
 */

import { act, render, screen } from '@testing-library/react';
import { useTranslation } from 'react-i18next';
import { beforeEach, describe, expect, it } from 'vitest';

import i18n, { LANGUAGES, setLanguage } from './index';
import en from './en.json';
import hr from './hr.json';

/** Every leaf path in a translation file, as dotted keys. */
function leaves(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    leaves(child, prefix ? `${prefix}.${key}` : key),
  );
}

/** Plural suffixes differ by language, so they are compared as one key. */
const stripPlural = (key: string) => key.replace(/_(one|few|many|other)$/, '');

function Probe() {
  const { t } = useTranslation();
  return (
    <div>
      <span data-testid="title">{t('search.title')}</span>
      <span data-testid="run">{t('search.run')}</span>
      <span data-testid="status">{t('status.applied')}</span>
    </div>
  );
}

describe('translations', () => {
  beforeEach(() => {
    localStorage.clear();
    setLanguage('en');
  });

  it('offers both languages', () => {
    expect(LANGUAGES.map((language) => language.code)).toEqual(['en', 'hr']);
  });

  it('has no holes in either language', () => {
    const english = new Set(leaves(en).map(stripPlural));
    const croatian = new Set(leaves(hr).map(stripPlural));

    expect([...english].filter((key) => !croatian.has(key))).toEqual([]);
    expect([...croatian].filter((key) => !english.has(key))).toEqual([]);
  });

  it('renders English by default', () => {
    render(<Probe />);
    expect(screen.getByTestId('title')).toHaveTextContent('Search');
    expect(screen.getByTestId('status')).toHaveTextContent('Applied');
  });

  it('switches every string at once, not just some', async () => {
    const { rerender } = render(<Probe />);
    act(() => setLanguage('hr'));
    rerender(<Probe />);

    expect(screen.getByTestId('title')).toHaveTextContent('Pretraga');
    expect(screen.getByTestId('run')).toHaveTextContent('Pokreni pretragu');
    expect(screen.getByTestId('status')).toHaveTextContent('Prijavljeno');
  });

  it('remembers the choice', () => {
    setLanguage('hr');
    expect(localStorage.getItem('jobsheet.language')).toBe('hr');
  });

  it('sets the document language, so screen readers pronounce it right', () => {
    setLanguage('hr');
    expect(document.documentElement.lang).toBe('hr');
  });

  it('counts in Croatian the way Croatian counts', () => {
    /** hr has one/few/other where English has one/other; 2 must not read as "2 oglas". */
    setLanguage('hr');
    expect(i18n.t('common.jobs', { count: 1 })).toBe('1 oglas');
    expect(i18n.t('common.jobs', { count: 3 })).toBe('3 oglasa');
    expect(i18n.t('common.jobs', { count: 11 })).toBe('11 oglasa');
  });
});
