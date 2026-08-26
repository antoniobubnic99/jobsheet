/**
 * The eight questions the wizard asks, one component each.
 *
 * They live apart from the wizard that walks through them because the walking
 * -- which step, what "next" means, when finishing is allowed -- is a different
 * job from the asking, and keeping them in one file would have made a screen
 * nobody wants to change.
 *
 * Every field has a working default, so a person who reads nothing and presses
 * next eight times still ends up with a search that runs. The questions are
 * ordered from the one everybody can answer ("what job?") to the ones only
 * somebody who has been hunting for a month knows they want.
 */

import { useTranslation } from 'react-i18next';

import type { KeywordGroup, SearchProfile, SearchSetup, SourceManifest } from '@/lib/types';
import { ChipInput, Empty, Labelled, Loading, Problem } from '@/components/primitives';
import KeywordGroups from '@/components/KeywordGroups';
import SourceCard from '@/components/SourceCard';

export interface StepProps {
  setup: SearchSetup;
  onChange: (patch: Partial<SearchSetup>) => void;
  onProfile: (patch: Partial<SearchProfile>) => void;
}

/* ------------------------------------------------------------------ 1 of 8 */

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

/* ------------------------------------------------------------------ 2 of 8 */

export function StepKeywords({ setup, onProfile }: StepProps) {
  return (
    <KeywordGroups
      groups={setup.profile.keyword_groups}
      onChange={(keyword_groups) => onProfile({ keyword_groups })}
    />
  );
}

/* ------------------------------------------------------------------ 3 of 8 */

export function StepWhere({ setup, onProfile }: StepProps) {
  const { t } = useTranslation();
  const profile = setup.profile;

  return (
    <div className="grid gap-[var(--gap-wide)]">
      <Labelled label={t('welcome.where.locations')} hint={t('welcome.where.locationsHint')}>
        <ChipInput
          ariaLabel={t('welcome.where.locations')}
          values={profile.locations}
          placeholder={t('search.locationPlaceholder')}
          onChange={(locations) => onProfile({ locations })}
        />
      </Labelled>

      <Labelled label={t('welcome.where.regions')} hint={t('welcome.where.regionsHint')}>
        <ChipInput
          ariaLabel={t('welcome.where.regions')}
          values={profile.regions}
          placeholder={t('welcome.where.regionsPlaceholder')}
          onChange={(regions) => onProfile({ regions })}
        />
      </Labelled>

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

/* ------------------------------------------------------------------ 4 of 8 */

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

/* ------------------------------------------------------------------ 5 of 8 */

export function StepExclusions({ setup, onProfile }: StepProps) {
  const { t } = useTranslation();
  const profile = setup.profile;

  return (
    <div className="grid gap-[var(--gap-wide)]">
      <Labelled label={t('welcome.no.employers')} hint={t('welcome.no.employersHint')}>
        <ChipInput
          ariaLabel={t('welcome.no.employers')}
          values={profile.excluded_employers}
          onChange={(excluded_employers) => onProfile({ excluded_employers })}
        />
      </Labelled>

      <Labelled label={t('welcome.no.types')} hint={t('welcome.no.typesHint')}>
        <ChipInput
          ariaLabel={t('welcome.no.types')}
          values={profile.excluded_employment_types}
          onChange={(excluded_employment_types) => onProfile({ excluded_employment_types })}
        />
      </Labelled>

      {/* Directly beneath the blocklist, and not by accident: in Croatian
          "na neodređeno" contains "određeno", so blocking fixed-term contracts
          silently blocks every permanent one too. The allowlist is the fix, and
          it is no use to anybody who never finds out it exists. */}
      <Labelled label={t('welcome.no.allowlist')} hint={t('welcome.no.allowlistHint')}>
        <ChipInput
          ariaLabel={t('welcome.no.allowlist')}
          values={profile.employment_type_allowlist}
          onChange={(employment_type_allowlist) => onProfile({ employment_type_allowlist })}
        />
      </Labelled>

      <Labelled label={t('welcome.no.schedules')} hint={t('welcome.no.schedulesHint')}>
        <ChipInput
          ariaLabel={t('welcome.no.schedules')}
          values={profile.excluded_schedules}
          onChange={(excluded_schedules) => onProfile({ excluded_schedules })}
        />
      </Labelled>
    </div>
  );
}

/* ------------------------------------------------------------------ 6 of 8 */

/** `flags` is a name and a list of words, which is exactly a keyword group. */
const flagsToGroups = (flags: Record<string, string[]>): KeywordGroup[] =>
  Object.entries(flags).map(([name, terms]) => ({ name, terms }));

const groupsToFlags = (groups: KeywordGroup[]): Record<string, string[]> =>
  Object.fromEntries(
    groups.filter((group) => group.name.trim()).map((group) => [group.name.trim(), group.terms]),
  );

export function StepFinePrint({ setup, onProfile }: StepProps) {
  const { t } = useTranslation();

  return (
    <div className="grid gap-[var(--gap-wide)]">
      <Labelled label={t('welcome.fine.evidence')} hint={t('welcome.fine.evidenceHint')}>
        <ChipInput
          ariaLabel={t('welcome.fine.evidence')}
          values={setup.profile.description_match_requires}
          onChange={(description_match_requires) => onProfile({ description_match_requires })}
        />
      </Labelled>

      <div>
        <span className="eyebrow mb-[var(--gap-hair)] block">{t('welcome.fine.flags')}</span>
        <p className="mb-[var(--gap-tight)] max-w-[62ch] text-[var(--text-micro)] text-[var(--ink-faint)]">
          {t('welcome.fine.flagsHint')}
        </p>
        <KeywordGroups
          groups={flagsToGroups(setup.profile.flags)}
          onChange={(groups) => onProfile({ flags: groupsToFlags(groups) })}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ 7 of 8 */

export function StepSources({
  setup,
  onChange,
  sources,
  loading,
  error,
  onRetry,
  locale,
}: StepProps & {
  sources: SourceManifest[];
  loading: boolean;
  error: string;
  onRetry: () => void;
  locale: string;
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

  if (loading) return <Loading />;
  if (error) return <Problem message={error} onRetry={onRetry} />;
  if (sources.length === 0) return <Empty>{t('common.nothing')}</Empty>;

  return (
    <div className="grid gap-[var(--gap-tight)] sm:grid-cols-2">
      {sources.map((source) => (
        <SourceCard
          key={source.id}
          source={source}
          chosen={source.id in chosen}
          params={chosen[source.id] ?? {}}
          onToggle={toggle}
          onParams={setParams}
          locale={locale}
        />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ 8 of 8 */

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

  return (
    <div className="grid gap-[var(--gap-wide)]">
      <Labelled label={t('welcome.workbook.label')} hint={t('welcome.workbook.hint')}>
        <input
          className="field mono text-[var(--text-small)]"
          value={workbook}
          spellCheck={false}
          placeholder={defaultPath}
          onChange={(event) => onWorkbook(event.target.value)}
        />
      </Labelled>

      {problem ? (
        <p
          role="alert"
          className="border-l-[3px] pl-[var(--gap-tight)] text-[var(--text-small)]"
          style={{ borderLeftColor: 'var(--bad)' }}
        >
          {problem}
        </p>
      ) : null}

      {/* The summary reads back what the wizard understood, in a sentence. Eight
          screens of fields are easy to lose track of, and "so: X in Y" is the
          cheapest way to catch the one that was filled in wrong. */}
      <div className="panel-sunk p-[var(--gap-wide)]">
        <p className="eyebrow mb-[var(--gap-tight)]">{t('welcome.summary.label')}</p>
        <dl className="grid gap-[var(--gap-tight)] text-[var(--text-small)] sm:grid-cols-[10rem_1fr]">
          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.looking')}</dt>
          <dd>{setup.headline || t('welcome.summary.anything')}</dd>

          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.terms')}</dt>
          <dd>{terms.length ? terms.join(', ') : t('welcome.summary.anything')}</dd>

          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.where')}</dt>
          <dd>
            {setup.profile.locations.length
              ? setup.profile.locations.join(', ')
              : t('welcome.summary.anywhere')}
          </dd>

          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.sources')}</dt>
          <dd className="mono">
            {setup.sources.map((one) => one.source_id).join(', ') || '—'}
          </dd>

          <dt className="text-[var(--ink-faint)]">{t('welcome.summary.freshness')}</dt>
          <dd>
            {t('welcome.summary.days', { count: setup.profile.max_age_days })}
          </dd>
        </dl>
      </div>
    </div>
  );
}
