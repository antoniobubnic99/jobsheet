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

import type { SearchProfile, SourceChoice, SourceManifest } from '@/lib/types';

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

/**
 * Whether every field a source marks `required` actually has a value.
 *
 * The run button used to check only "is any source ticked", so a Workable or
 * Lever card left with an empty slug would still start a run -- and then fail
 * with nothing on screen to say why. This is the check that catches it before
 * the request ever leaves the browser.
 */
export function sourceIsReady(source: SourceManifest, params: Record<string, unknown>): boolean {
  return source.params
    .filter((spec) => spec.required)
    .every((spec) => {
      const value = params[spec.name];
      return typeof value === 'string' ? value.trim() !== '' : value != null && value !== '';
    });
}

/** Every saved source choice passes {@link sourceIsReady} against its manifest.
    A source id the manifest no longer knows about is treated as ready --
    there is nothing left to validate it against. */
export function allSourcesReady(
  sources: SourceChoice[],
  manifests: SourceManifest[],
): boolean {
  const byId = new Map(manifests.map((one) => [one.id, one]));
  return sources.every((choice) => {
    const manifest = byId.get(choice.source_id);
    return !manifest || sourceIsReady(manifest, choice.params ?? {});
  });
}

/** The one parameter name, per ATS source, that is the board/account slug a
    person copies out of the company's careers-page address. */
const ATS_SLUG_PARAM: Record<string, string> = {
  workable: 'account',
  ashby: 'board',
  greenhouse: 'board',
  lever: 'company',
};

/**
 * A slug field forgives a pasted full address.
 *
 * The four ATS sources all ask for the same kind of value -- the last segment
 * of a URL like `jobs.lever.co/acme` -- and pasting the whole address instead
 * of just `acme` is an easy, common mistake for exactly the fields these
 * sources need. Anything else is returned trimmed and otherwise untouched.
 */
export function normalizeAtsSlug(sourceId: string, paramName: string, value: string): string {
  const trimmed = value.trim();
  if (ATS_SLUG_PARAM[sourceId] !== paramName || !trimmed.includes('/')) return trimmed;
  const withoutHost = trimmed.replace(/^https?:\/\//i, '').replace(/^[^/]+\//, '');
  return withoutHost.split(/[/?#]/)[0] || trimmed;
}
