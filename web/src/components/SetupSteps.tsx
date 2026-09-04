/**
 * The seven questions the wizard asks, one component each.
 *
 * They live apart from the wizard that walks through them because the walking
 * -- which step, what "next" means, when finishing is allowed -- is a different
 * job from the asking, and keeping both in one file would have made a screen
 * nobody wants to change.
 *
 * Every field has a working default, so somebody who reads nothing and presses
 * next seven times still ends up with a search that runs. The questions are
 * ordered from the one everybody can answer ("what job?") to the ones only
 * somebody who has been hunting for a month knows they want.
 *
 * Two rules the steps share, learned from watching the first version being used:
 *
 * * **Where there is a list, offer it.** A place or an employer typed by hand is
 *   where a search quietly stops working -- one misspelling and the filter
 *   throws every ad away, with nothing anywhere to say why. Free text still
 *   goes in: the sources are not all Croatian.
 * * **Warn, never block.** Not one field here can put the wizard in a state
 *   where "Next" is refused. The only thing the whole wizard insists on is a
 *   source, because a search with nowhere to look is not a search.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { api } from '@/lib/api';
import type { SearchProfile, SearchSetup, SourceManifest } from '@/lib/types';
import { deriveSourceParams } from '@/lib/sourceDefaults';
import {
  ChipInput,
  Empty,
  Labelled,
  Loading,
  Note,
  Problem,
  Toggle,
} from '@/components/primitives';
import Combobox from '@/components/Combobox';
import FolderPicker from '@/components/FolderPicker';
import KeywordGroups from '@/components/KeywordGroups';
import SourceBulkActions from '@/components/SourceBulkActions';
import SourceCard from '@/components/SourceCard';

export interface StepProps {
  setup: SearchSetup;
  onChange: (patch: Partial<SearchSetup>) => void;
  onProfile: (patch: Partial<SearchProfile>) => void;
}

/* ------------------------------------------------------------------ 1 of 7 */

export function StepHeadline({ setup, onChange }: StepProps) {
  const { t } = useTranslation();
  return (
    <Labelled label={t('welcome.headline.label')} hint={t('welcome.headline.hint')}>
      <input
        className="field"
        autoFocus
        value={setup.headline}
        placeholder={t('welcome.headline.placeholder')}
        onChange={(event) => onChange({ headline: event.target.value })}
      />
    </Labelled>
  );
}

/* ------------------------------------------------------------------ 2 of 7 */

/**
 * Words that plausibly mean the job somebody just described.
 *
 * Deliberately dumb: the headline itself, and its stems. There is no dictionary
 * here and there should not be one -- a wrong suggestion is worse than none,
 * because the whole point of this screen is that the user learns what a keyword
 * *is*. The stem is the lesson: "geodet" catches geodet and geodetski both.
 */
function suggestTerms(headline: string): string[] {
  const words = headline
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter((word) => word.length > 3);

  const stems = words.map((word) =>
    // Croatian inflects heavily, so the useful term is usually a syllable or two
    // shorter than the word somebody typed. Six characters is long enough to
    // stay specific and short enough to catch the endings.
    word.length > 6 ? word.slice(0, Math.max(5, word.length - 2)) : word,
  );
  return [...new Set([...words, ...stems])].slice(0, 6);
}

export function StepKeywords({ setup, onProfile }: StepProps) {
  const { t } = useTranslation();
  const groups = setup.profile.keyword_groups;

  const headline = setup.headline.trim();
  const suggestions = useMemo(() => suggestTerms(headline), [headline]);
  const first = groups[0];

  /**
   * Fill the first group in from the headline. Offered as a button rather than
   * done quietly: a field that fills itself is a field the user did not write,
   * and this is the one step whose job is to be understood.
   */
  const apply = () =>
    onProfile({
      keyword_groups: groups.map((group, index) =>
        index === 0
          ? {
              name: group.name.trim() || sentenceCase(headline),
              terms: [...new Set([...group.terms, ...suggestions])],
            }
          : group,
      ),
    });

  const named = groups.filter((group) => group.name.trim());
  const withWords = groups.filter((group) => group.name.trim() && group.terms.length);
  const anyWords = groups.some((group) => group.terms.length);

  return (
    <div className="grid gap-[var(--gap-wide)]">
      {/* What a keyword actually is, in the words of the mistake it prevents.
          This is the step people said they did not understand. */}
      <Note>{t('welcome.keywords.stems')}</Note>

      {headline && suggestions.length && first && !first.terms.length ? (
        <div className="panel-sunk flex flex-wrap items-center gap-[var(--gap-tight)] p-[var(--gap)]">
          <span className="text-[var(--text-small)]">
            {t('welcome.keywords.offer', { headline })}
          </span>
          <span className="flex flex-wrap gap-[var(--gap-hair)]">
            {suggestions.map((word) => (
              <span
                key={word}
                className="mono rounded-[var(--radius-sharp)] bg-[var(--accent-soft)] px-[0.4rem] text-[var(--text-small)]"
              >
                {word}
              </span>
            ))}
          </span>
          <button type="button" className="btn btn-quiet" onClick={apply}>
            {t('welcome.keywords.accept')}
          </button>
        </div>
      ) : null}

      <KeywordGroups
        groups={groups}
        onChange={(keyword_groups) => onProfile({ keyword_groups })}
      />

      {/* What this will do, said in the spreadsheet's own terms. Eight fields
          later, "so: category Geodet" is the cheapest way to catch a mistake. */}
      {withWords.length ? (
        <p className="text-[var(--text-small)] text-[var(--ink-soft)]">
          {t('welcome.keywords.result')}{' '}
          {withWords.map((group, index) => (
            <span key={group.name}>
              {index ? ', ' : ''}
              <strong>{group.name.trim()}</strong>
            </span>
          ))}
        </p>
      ) : null}

      {!anyWords ? (
        <Note tone="warn">{t('welcome.keywords.noneWarning')}</Note>
      ) : null}

      {named.length > withWords.length ? (
        <Note tone="warn">{t('welcome.keywords.halfTyped')}</Note>
      ) : null}
    </div>
  );
}

/** "geodet" -> "Geodet". The category the user sees should look written, not typed. */
const sentenceCase = (text: string) =>
  text ? text[0]!.toUpperCase() + text.slice(1) : text;

/* ------------------------------------------------------------------ 3 of 7 */

export function StepWhere({ setup, onProfile }: StepProps) {
  const { t } = useTranslation();
  const profile = setup.profile;

  return (
    <div className="grid gap-[var(--gap-wide)]">
      <Labelled label={t('welcome.where.locations')} hint={t('welcome.where.locationsHint')}>
        <Combobox
          ariaLabel={t('welcome.where.locations')}
          values={profile.locations}
          placeholder={t('search.locationPlaceholder')}
          onChange={(locations) => onProfile({ locations })}
          suggest={async (q) => {
            const found = await api.places(q);
            return found.places.map((place) => ({ value: place.name, note: place.county }));
          }}
        />
      </Labelled>

      <Labelled label={t('welcome.where.regions')} hint={t('welcome.where.regionsHint')}>
        <Combobox
          ariaLabel={t('welcome.where.regions')}
          values={profile.regions}
          placeholder={t('welcome.where.regionsPlaceholder')}
          onChange={(regions) => onProfile({ regions })}
          suggest={async (q) => {
            const found = await api.places(q, 'county');
            return found.places.map((place) => ({ value: place.name }));
          }}
        />
      </Labelled>

      {profile.regions.length ? (
        <Note>{t('welcome.where.regionsAreASecondChoice')}</Note>
      ) : null}

      <Labelled label={t('welcome.where.remote')} hint={t('welcome.where.remoteHint')}>
        <ChipInput
          ariaLabel={t('welcome.where.remote')}
          values={profile.remote_terms}
          onChange={(remote_terms) => onProfile({ remote_terms })}
        />
      </Labelled>
    </div>
  );
}

/* ------------------------------------------------------------------ 4 of 7 */

export function StepFreshness({ setup, onProfile }: StepProps) {
  const { t } = useTranslation();
  return (
    <Labelled label={t('welcome.freshness.label')} hint={t('welcome.freshness.hint')}>
      <div className="flex items-center gap-[var(--gap-tight)]">
        <input
          className="field w-[6rem]"
          type="number"
          min={1}
          max={365}
          value={setup.profile.max_age_days}
          onChange={(event) =>
            onProfile({ max_age_days: Math.max(1, Number(event.target.value) || 1) })
          }
        />
        <span className="text-[var(--text-small)] text-[var(--ink-soft)]">
          {t('search.days')}
        </span>
      </div>
    </Labelled>
  );
}

/* ------------------------------------------------------------------ 5 of 7 */

/**
 * The contracts offered as tick boxes, in the wording Croatian ads use.
 *
 * Matched as stems against whatever the ad says, like every other term in
 * JobSheet, which is why "praksa" is enough to catch "Praksa/pripravništvo".
 * The list is a starting point and not a vocabulary: anything else goes in the
 * free-text field beside it.
 */
const CONTRACTS = [
  'neodređeno',
  'određeno',
  'puno radno vrijeme',
  'nepuno radno vrijeme',
  'sezonski',
  'praksa',
  'ugovor o djelu',
  'student',
] as const;

export function StepEmployers({ setup, onProfile }: StepProps) {
  const { t } = useTranslation();
  const profile = setup.profile;

  const wanted = profile.wanted_employment_types;
  const toggleContract = (term: string, on: boolean) =>
    onProfile({
      wanted_employment_types: on
        ? [...wanted, term]
        : wanted.filter((one) => one !== term),
    });

  const employers = async (q: string) => {
    const found = await api.companies(q);
    return found.companies.map((one) => ({
      value: one.name,
      note: t('welcome.employers.seenTimes', { count: one.count }),
    }));
  };

  return (
    <div className="grid gap-[var(--gap-wide)]">
      <Labelled label={t('welcome.employers.dream')} hint={t('welcome.employers.dreamHint')}>
        <Combobox
          ariaLabel={t('welcome.employers.dream')}
          values={profile.dream_employers}
          onChange={(dream_employers) => onProfile({ dream_employers })}
          suggest={employers}
        />
      </Labelled>

      <Labelled label={t('welcome.employers.skip')} hint={t('welcome.employers.skipHint')}>
        <Combobox
          ariaLabel={t('welcome.employers.skip')}
          values={profile.excluded_employers}
          onChange={(excluded_employers) => onProfile({ excluded_employers })}
          suggest={employers}
        />
      </Labelled>

      <div>
        <span className="eyebrow mb-[var(--gap-hair)] block">
          {t('welcome.employers.contracts')}
        </span>
        <p className="mb-[var(--gap-tight)] max-w-[62ch] text-[var(--text-micro)] text-[var(--ink-faint)]">
          {t('welcome.employers.contractsHint')}
        </p>
        <div className="grid gap-[var(--gap-hair)] sm:grid-cols-2">
          {CONTRACTS.map((term) => (
            <Toggle
              key={term}
              label={t(`welcome.employers.contract.${term.replace(/\s/g, '_')}`)}
              checked={wanted.includes(term)}
              onChange={(on) => toggleContract(term, on)}
            />
          ))}
        </div>
        {wanted.length ? (
          <div className="mt-[var(--gap-tight)]">
            {/* The fail-open rule, said out loud where the choice is made. Half
                the feeds never state a contract type, and somebody who ticked a
                box would otherwise wonder why those ads still turn up. */}
            <Note>{t('welcome.employers.unstatedArePassed')}</Note>
          </div>
        ) : null}
      </div>

      <Labelled label={t('welcome.employers.schedules')} hint={t('welcome.employers.schedulesHint')}>
        <ChipInput
          ariaLabel={t('welcome.employers.schedules')}
          values={profile.excluded_schedules}
          onChange={(excluded_schedules) => onProfile({ excluded_schedules })}
        />
      </Labelled>
    </div>
  );
}

/* ------------------------------------------------------------------ 6 of 7 */

export function StepSources({
  setup,
  onChange,
  sources,
  countries,
  loading,
  error,
  onRetry,
  locale,
  countyFeeds,
}: StepProps & {
  sources: SourceManifest[];
  countries: string[];
  loading: boolean;
  error: string;
  onRetry: () => void;
  locale: string;
  /** HZZ feed numbers implied by the counties chosen on step 3. */
  countyFeeds: number[];
}) {
  const { t } = useTranslation();
  const chosen = Object.fromEntries(setup.sources.map((one) => [one.source_id, one.params]));

  const toggle = (id: string, defaults: Record<string, unknown>) =>
    onChange({
      sources:
        id in chosen
          ? setup.sources.filter((one) => one.source_id !== id)
          : [...setup.sources, { source_id: id, params: defaults }],
    });

  const setParams = (id: string, params: Record<string, unknown>) =>
    onChange({
      sources: setup.sources.map((one) => (one.source_id === id ? { ...one, params } : one)),
    });

  /** Tick exactly this set, keeping the parameters of anything already ticked. */
  const choose = (wanted: SourceManifest[]) =>
    onChange({
      sources: wanted.map((source) => ({
        source_id: source.id,
        params: chosen[source.id] ?? deriveSourceParams(source, setup.profile, countyFeeds),
      })),
    });

  const grouped = useMemo(() => {
    const global = sources.filter((source) => source.is_global);
    const byCountry = new Map<string, SourceManifest[]>();
    for (const source of sources) {
      if (source.is_global) continue;
      const key = source.country ?? '';
      byCountry.set(key, [...(byCountry.get(key) ?? []), source]);
    }
    return { global, byCountry };
  }, [sources]);

  if (loading) return <Loading />;
  if (error) return <Problem message={error} onRetry={onRetry} />;
  if (sources.length === 0) return <Empty>{t('common.nothing')}</Empty>;

  const card = (source: SourceManifest) => (
    <SourceCard
      key={source.id}
      source={source}
      chosen={source.id in chosen}
      params={chosen[source.id] ?? {}}
      onToggle={(id) => toggle(id, deriveSourceParams(source, setup.profile, countyFeeds))}
      onParams={setParams}
      locale={locale}
    />
  );

  return (
    <div className="grid gap-[var(--gap-wide)]">
      {/* Fourteen sources in one flat grid is a wall. Three buttons and a
          heading per country turn it into a choice somebody can make. */}
      <SourceBulkActions
        sources={sources}
        countries={countries}
        chosenCount={setup.sources.length}
        onChoose={choose}
      />

      {grouped.global.length ? (
        <div>
          <h3 className="eyebrow mb-[var(--gap-tight)]">{t('search.global')}</h3>
          <div className="grid gap-[var(--gap-tight)] sm:grid-cols-2">
            {grouped.global.map(card)}
          </div>
        </div>
      ) : null}

      {[...grouped.byCountry.entries()].map(([country, list]) => (
        <div key={country}>
          <h3 className="eyebrow mb-[var(--gap-tight)]">
            {t('search.byCountry')} · <span className="mono">{country}</span>
          </h3>
          <div className="grid gap-[var(--gap-tight)] sm:grid-cols-2">{list.map(card)}</div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ 7 of 7 */

/** Everything after the last separator: the file name, without the folder. */
const fileOf = (path: string) => path.split(/[\\/]/).pop() ?? '';

/** Everything before it, with no trailing separator. */
const folderOf = (path: string) =>
  path.slice(0, path.length - fileOf(path).length).replace(/[\\/]+$/, '');

/** Whichever separator this machine's own paths already use. */
const join = (folder: string, name: string) =>
  `${folder}${folder.includes('\\') || !folder.includes('/') ? '\\' : '/'}${name}`;

const DEFAULT_NAME = 'jobs.xlsx';

export function StepWorkbook({
  setup,
  workbook,
  onWorkbook,
  defaultPath,
  problem,
}: {
  setup: SearchSetup;
  workbook: string;
  onWorkbook: (next: string) => void;
  defaultPath: string;
  problem: string;
}) {
  const { t } = useTranslation();
  const terms = setup.profile.keyword_groups.flatMap((group) => group.terms);

  // Two halves of one answer. The folder is picked, the name is typed, and an
  // untouched step leaves `workbook` empty -- which is how the server is told
  // "wherever you keep mine", still the right answer for most people.
  const [folder, setFolder] = useState(() => folderOf(workbook));
  const [name, setName] = useState(() => fileOf(workbook));

  const settle = (nextFolder: string, nextName: string) => {
    setFolder(nextFolder);
    setName(nextName);
    if (!nextFolder && !nextName) {
      onWorkbook('');
      return;
    }
    onWorkbook(join(nextFolder || folderOf(defaultPath), nextName || DEFAULT_NAME));
  };

  /**
   * What is wrong with the path as it stands, worked out while it is typed.
   *
   * The same rules the server enforces, under the same error codes, so the
   * wording is the wording that would have appeared at the end -- except that
   * it now arrives before somebody has walked to the end to find out. Whether
   * the folder exists is still the server's word: only it can know.
   */
  const trouble = useMemo(() => {
    const path = workbook.trim();
    if (!path) return '';
    if (/[\\/]$/.test(path)) return t('auth.errors.workbook_is_a_folder');
    if (!path.toLowerCase().endsWith('.xlsx')) return t('auth.errors.workbook_not_xlsx');
    return '';
  }, [workbook, t]);

  return (
    <div className="grid gap-[var(--gap-wide)]">
      <div>
        <span className="eyebrow mb-[var(--gap-hair)] block">
          {t('welcome.workbook.folder')}
        </span>
        <FolderPicker
          value={folder || folderOf(defaultPath)}
          onChange={(picked) => settle(picked, name)}
        />
      </div>

      <Labelled label={t('welcome.workbook.fileName')} hint={t('welcome.workbook.hint')}>
        <input
          className="field mono text-[var(--text-small)]"
          value={name}
          spellCheck={false}
          placeholder={fileOf(defaultPath) || DEFAULT_NAME}
          onChange={(event) => settle(folder, event.target.value)}
        />
      </Labelled>

      <p className="mono break-all text-[var(--text-micro)] text-[var(--ink-faint)]">
        {workbook || defaultPath}
      </p>

      {problem || trouble ? (
        <p
          role="alert"
          className="border-l-[3px] pl-[var(--gap-tight)] text-[var(--text-small)]"
          style={{ borderLeftColor: 'var(--bad)' }}
        >
          {problem || trouble}
        </p>
      ) : null}

      {/* The summary reads back what the wizard understood, in a sentence.
          Seven screens of fields are easy to lose track of, and "so: X in Y" is
          the cheapest way to catch the one that was filled in wrong. */}
      <div className="panel-sunk p-[var(--gap-wide)]">
        <p className="eyebrow mb-[var(--gap-tight)]">{t('welcome.summary.label')}</p>
        <dl className="grid gap-[var(--gap-tight)] text-[var(--text-small)] sm:grid-cols-[10rem_1fr]">
          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.looking')}</dt>
          <dd>{setup.headline || t('welcome.summary.anything')}</dd>

          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.terms')}</dt>
          <dd>{terms.length ? terms.join(', ') : t('welcome.summary.anything')}</dd>

          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.categories')}</dt>
          {/* Only the groups that will survive being saved. The old summary
              listed half-typed ones the submission then dropped, which is a
              summary that lies about the thing it is there to confirm. */}
          <dd>
            {keptCategories(setup).join(', ') || t('welcome.summary.none')}
          </dd>

          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.where')}</dt>
          <dd>
            {setup.profile.locations.length
              ? setup.profile.locations.join(', ')
              : t('welcome.summary.anywhere')}
          </dd>

          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.sources')}</dt>
          <dd className="mono">{setup.sources.map((one) => one.source_id).join(', ') || '—'}</dd>

          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.freshness')}</dt>
          <dd>{t('welcome.summary.days', { count: setup.profile.max_age_days })}</dd>
        </dl>
      </div>
    </div>
  );
}

/** The categories that will actually reach the spreadsheet. See the summary above. */
export const keptCategories = (setup: SearchSetup): string[] =>
  setup.profile.keyword_groups
    .filter((group) => group.name.trim() && group.terms.length)
    .map((group) => group.name.trim());
