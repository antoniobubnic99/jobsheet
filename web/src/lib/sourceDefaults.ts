/**
 * What a source starts with, before anyone touches its form.
 *
 * A source's `params` drive its fetch query, and the general search
 * requirements (`SearchProfile`) drive filtering afterward -- two different
 * jobs, which is why they are two different types (see the docstring atop
 * `pipeline.py` on the server). But a source whose field obviously means the
 * same thing as a profile field should not make the user say it twice: HZZ's
 * `counties` is `profile.regions`, wearing a different name.
 *
 * Every path that ticks a source -- one card, "select all", the wizard --
 * goes through `deriveSourceParams`, so the mapping only has to be right once
 * and only lives in one place.
 */

import type { SearchProfile, SourceManifest } from '@/lib/types';

/**
 * The same comparison the server makes (`jobsheet.core.matching.fold`).
 *
 * Only ever used to line a name the user typed up against a list of known
 * ones, never to decide anything on its own: a name that does not match
 * simply contributes nothing, rather than throwing.
 */
export const fold = (text: string) =>
  text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[đĐ]/g, 'd')
    .toLowerCase()
    .replace(/\bzupanija\b/, '')
    .trim();

/** The HZZ feed numbers implied by the counties named in the profile. */
export function deriveCountyFeeds(
  regions: string[],
  counties: { name: string; feed: number }[],
): number[] {
  const byName = new Map(counties.map((one) => [fold(one.name), one.feed]));
  return regions
    .map((region) => byName.get(fold(region)))
    .filter((feed): feed is number => typeof feed === 'number');
}

/**
 * The parameters a source starts with when it is ticked.
 *
 * Starts from the manifest's own defaults, then overlays whatever the
 * profile already answered for the handful of fields with an obvious match.
 * A source with nothing in common with the profile -- an ATS board slug, a
 * source with no params at all -- is left untouched: there is nothing honest
 * to fill in for it.
 */
export function deriveSourceParams(
  source: SourceManifest,
  profile: SearchProfile,
  countyFeeds: number[],
): Record<string, unknown> {
  const params = Object.fromEntries(
    source.params
      .filter((spec) => spec.default != null)
      .map((spec) => [spec.name, spec.default]),
  );

  switch (source.id) {
    case 'hzz':
      // They already said where they want to work; asking again would be rude.
      if (countyFeeds.length) params.counties = countyFeeds.map(String);
      break;

    case 'narodne_novine': {
      const terms = [...new Set(profile.keyword_groups.flatMap((group) => group.terms))];
      // Left unset, not `''`, when the profile has none: the field stays
      // required and the form still asks for it, exactly as it does today.
      if (terms.length) params.terms = terms.join(', ');
      params.days = profile.max_age_days;
      break;
    }

    case 'selekcija':
      params.days = profile.max_age_days;
      break;

    default:
      break;
  }

  return params;
}
