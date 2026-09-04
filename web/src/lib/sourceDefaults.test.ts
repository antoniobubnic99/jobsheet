import { describe, expect, it } from 'vitest';

import { deriveCountyFeeds, deriveSourceParams } from '@/lib/sourceDefaults';
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
