import { describe, expect, it } from 'vitest';

import {
  allSourcesReady,
  deriveCountyFeeds,
  deriveSourceParams,
  normalizeAtsSlug,
  sourceIsReady,
} from '@/lib/sourceDefaults';
import { EMPTY_PROFILE, type ParamSpec, type SearchProfile, type SourceManifest } from '@/lib/types';

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

function source(overrides: Partial<SourceManifest>): SourceManifest {
  return {
    id: 'test',
    name: 'Test',
    homepage: '',
    description: '',
    country: null,
    params: [],
    rate_limit: 1,
    supports_enrich: false,
    needs_credentials: false,
    is_global: true,
    health: null,
    ...overrides,
  };
}

describe('deriveCountyFeeds', () => {
  it('matches counties by folded name, diacritics and all', () => {
    const feeds = deriveCountyFeeds(
      ['Istarska županija', 'Grad Zagreb'],
      [
        { name: 'Istarska županija', feed: 5 },
        { name: 'Grad Zagreb', feed: 4 },
        { name: 'Ličko-senjska županija', feed: 9 },
      ],
    );
    expect(feeds).toEqual([5, 4]);
  });

  it('leaves out a region with nothing to match, rather than throwing', () => {
    const feeds = deriveCountyFeeds(['Nepostojeća županija'], [{ name: 'Grad Zagreb', feed: 4 }]);
    expect(feeds).toEqual([]);
  });
});

describe('deriveSourceParams', () => {
  const profile: SearchProfile = {
    ...EMPTY_PROFILE,
    keyword_groups: [
      { name: 'Geodezija', terms: ['geodetski', 'katastar'] },
      { name: 'Urbanizam', terms: ['urbanizam', 'katastar'] },
    ],
    regions: ['Istarska županija'],
    max_age_days: 14,
  };

  it('fills HZZ counties from the feeds implied by the profile', () => {
    const hzz = source({
      id: 'hzz',
      params: [spec({ name: 'counties', kind: 'multiselect', required: true, default: [4] })],
    });
    expect(deriveSourceParams(hzz, profile, [5])).toEqual({ counties: ['5'] });
  });

  it('keeps HZZ on its manifest default when no county matched', () => {
    const hzz = source({
      id: 'hzz',
      params: [spec({ name: 'counties', kind: 'multiselect', required: true, default: [4] })],
    });
    expect(deriveSourceParams(hzz, profile, [])).toEqual({ counties: [4] });
  });

  it('joins the profile keywords into Narodne novine terms, deduplicated', () => {
    const nn = source({
      id: 'narodne_novine',
      params: [
        spec({ name: 'terms', required: true, default: null }),
        spec({ name: 'days', kind: 'number', default: 30 }),
        spec({ name: 'max_pages', kind: 'number', default: 30 }),
      ],
    });
    expect(deriveSourceParams(nn, profile, [])).toEqual({
      terms: 'geodetski, katastar, urbanizam',
      days: 14,
      max_pages: 30,
    });
  });

  it('leaves Narodne novine terms unset -- not empty -- when the profile has none', () => {
    // Required stays required: an empty string would silently pass validation
    // that an absent value still catches, forcing the user to type something.
    const nn = source({
      id: 'narodne_novine',
      params: [
        spec({ name: 'terms', required: true, default: null }),
        spec({ name: 'days', kind: 'number', default: 30 }),
      ],
    });
    const params = deriveSourceParams(nn, EMPTY_PROFILE, []);
    expect(params).toEqual({ days: 30 });
    expect(params.terms).toBeUndefined();
  });

  it('fills Selekcija days from the profile', () => {
    const selekcija = source({
      id: 'selekcija',
      params: [spec({ name: 'days', kind: 'number', default: 45 })],
    });
    expect(deriveSourceParams(selekcija, profile, [])).toEqual({ days: 14 });
  });

  it('leaves a source with no params untouched', () => {
    const posaoHr = source({ id: 'posao_hr', params: [] });
    expect(deriveSourceParams(posaoHr, profile, [])).toEqual({});
  });

  it('leaves a source with nothing in common with the profile to its own defaults', () => {
    const greenhouse = source({
      id: 'greenhouse',
      params: [
        spec({ name: 'board', required: true, default: null }),
        spec({ name: 'remote_ok', kind: 'boolean', default: false }),
      ],
    });
    expect(deriveSourceParams(greenhouse, profile, [])).toEqual({ remote_ok: false });
  });
});

describe('sourceIsReady', () => {
  const greenhouse = source({
    id: 'greenhouse',
    params: [
      spec({ name: 'board', required: true, default: null }),
      spec({ name: 'remote_ok', kind: 'boolean', required: false, default: false }),
    ],
  });

  it('is not ready when a required field is missing', () => {
    expect(sourceIsReady(greenhouse, {})).toBe(false);
  });

  it('is not ready when a required field is only whitespace', () => {
    expect(sourceIsReady(greenhouse, { board: '   ' })).toBe(false);
  });

  it('is ready once every required field has a value', () => {
    expect(sourceIsReady(greenhouse, { board: 'gitlab' })).toBe(true);
  });

  it('does not require an optional field', () => {
    expect(sourceIsReady(greenhouse, { board: 'gitlab' })).toBe(true);
  });

  it('has nothing to check on a source with no required fields', () => {
    const rss = source({ id: 'rss', params: [] });
    expect(sourceIsReady(rss, {})).toBe(true);
  });
});

describe('allSourcesReady', () => {
  const greenhouse = source({
    id: 'greenhouse',
    params: [spec({ name: 'board', required: true, default: null })],
  });

  it('is false while any ticked source is missing a required value', () => {
    const ready = allSourcesReady(
      [
        { source_id: 'greenhouse', params: {} },
        { source_id: 'rss', params: { url: 'https://example.test/feed' } },
      ],
      [greenhouse],
    );
    expect(ready).toBe(false);
  });

  it('is true once every ticked source has what it needs', () => {
    const ready = allSourcesReady([{ source_id: 'greenhouse', params: { board: 'gitlab' } }], [
      greenhouse,
    ]);
    expect(ready).toBe(true);
  });

  it('treats a source id the manifest no longer lists as nothing to validate', () => {
    const ready = allSourcesReady([{ source_id: 'retired', params: {} }], [greenhouse]);
    expect(ready).toBe(true);
  });
});

describe('normalizeAtsSlug', () => {
  it('leaves a bare slug untouched, just trimmed', () => {
    expect(normalizeAtsSlug('lever', 'company', '  acme  ')).toBe('acme');
  });

  it('strips a pasted full URL down to the slug', () => {
    expect(normalizeAtsSlug('lever', 'company', 'https://jobs.lever.co/acme')).toBe('acme');
    expect(normalizeAtsSlug('workable', 'account', 'apply.workable.com/acme-inc')).toBe(
      'acme-inc',
    );
    expect(normalizeAtsSlug('greenhouse', 'board', 'https://job-boards.greenhouse.io/gitlab/')).toBe(
      'gitlab',
    );
    expect(normalizeAtsSlug('ashby', 'board', 'https://jobs.ashbyhq.com/ashby?utm=x')).toBe(
      'ashby',
    );
  });

  it('leaves a field that is not the slug param untouched', () => {
    expect(normalizeAtsSlug('greenhouse', 'company', 'https://example.test/x')).toBe(
      'https://example.test/x',
    );
  });

  it('leaves a non-ATS source untouched', () => {
    expect(normalizeAtsSlug('rss', 'url', 'https://example.test/feed')).toBe(
      'https://example.test/feed',
    );
  });
});
