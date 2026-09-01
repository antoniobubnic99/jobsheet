/**
 * 01 — Home.
 *
 * What this screen is for: somebody who has already answered the wizard's
 * questions opens JobSheet in the morning and wants one thing. So there is one
 * button, and it is large.
 *
 * The screen it replaced was the editor -- every source, every keyword, every
 * filter, laid out at once -- which meant the daily action was buried in a form
 * nobody needed to see again after the first day. The editor still exists, at
 * `/search/edit`, and is one link away.
 *
 * The summary at the bottom is deliberately read-only. It reads the same saved
 * setup the editor seeds itself from, so the two can never drift; showing
 * fields that look editable but are not would be worse than showing prose.
 */

import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { api, ApiError, DEFAULT_SETUP } from '@/lib/api';
import type { SearchSetup } from '@/lib/types';
import { screenNumber } from '@/lib/screens';
import { useSearchRun } from '@/lib/useSearchRun';
import { Loading, Note, ScreenHeader, Section } from '@/components/primitives';
import RunProgress from '@/components/RunProgress';

const EDITOR = '/search/edit';

/** One line of the summary. Absent facts are omitted, never shown as "none". */
function Fact({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="rule-b flex flex-wrap gap-x-[var(--gap)] gap-y-[var(--gap-hair)] py-[var(--gap-tight)] last:border-b-0">
      <dt className="eyebrow min-w-[8rem] shrink-0 text-[var(--ink-faint)]">{label}</dt>
      <dd className="min-w-0 flex-1 text-[var(--text-small)]">{value}</dd>
    </div>
  );
}

export default function HomeScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const run = useSearchRun();

  // The same query key the editor uses, so both read one cached answer and the
  // summary can never disagree with the form behind it.
  const setup = useQuery({
    queryKey: ['profiles', 'setup', DEFAULT_SETUP],
    queryFn: async () => {
      try {
        return await api.loadProfile<SearchSetup>('setup', DEFAULT_SETUP);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    retry: false,
  });

  const payload = setup.data?.payload;
  const profile = payload?.profile;
  const ready = Boolean(payload?.sources.length);

  const list = (values: string[] | undefined) => (values ?? []).join(' · ');

  return (
    <>
      <ScreenHeader
        number={screenNumber('search')}
        title={payload?.headline || t('home.title')}
        lede={t('home.lede')}
      />

      <Section label={t('home.today')}>
        <div className="flex flex-col gap-[var(--gap-tight)] sm:flex-row">
          <button
            type="button"
            className="btn btn-primary flex-[2] justify-center py-[var(--gap)] text-[var(--text-lead)]"
            disabled={!ready || run.state === 'running'}
            onClick={() => payload && run.start(payload.sources, payload.profile)}
          >
            {run.state === 'running' ? t('search.running') : t('search.run')}
          </button>
          <button
            type="button"
            className="btn btn-quiet flex-1 justify-center py-[var(--gap)]"
            onClick={() => navigate('/results')}
          >
            {t('home.openList')}
          </button>
        </div>

        {setup.isLoading ? <Loading /> : null}

        {/* An account that predates the wizard has no setup. It is not an
            error, it is a sentence pointing at the one screen that fixes it. */}
        {!setup.isLoading && !ready ? (
          <div className="mt-[var(--gap)]">
            <Note tone="warn">
              {t('home.nothingSetUp')}{' '}
              <button
                type="button"
                className="btn btn-bare px-0 underline"
                onClick={() => navigate(EDITOR)}
              >
                {t('home.edit')}
              </button>
            </Note>
          </div>
        ) : null}
      </Section>

      {run.state !== 'idle' ? (
        <RunProgress
          state={run.state}
          progress={run.progress}
          lines={run.lines}
          found={run.found}
          error={run.error}
          onStop={run.cancel}
          onRetry={() => payload && run.start(payload.sources, payload.profile)}
          onSeeResults={() =>
            navigate(run.recordedId ? `/results?run=${run.recordedId}` : '/results')
          }
        />
      ) : null}

      {profile ? (
        <Section
          label={t('home.summary')}
          aside={
            <button
              type="button"
              className="btn btn-quiet"
              onClick={() => navigate(EDITOR)}
            >
              {t('home.edit')}
            </button>
          }
        >
          <dl className="panel px-[var(--gap-wide)] py-[var(--gap-tight)]">
            <Fact label={t('welcome.summary.looking')} value={payload?.headline ?? ''} />
            <Fact
              label={t('welcome.summary.terms')}
              value={profile.keyword_groups
                .map((group) => `${group.name}: ${group.terms.join(', ')}`)
                .join(' · ')}
            />
            <Fact
              label={t('welcome.summary.where')}
              value={
                list([...profile.locations, ...profile.regions]) ||
                t('welcome.summary.anywhere')
              }
            />
            <Fact
              label={t('home.contracts')}
              value={list(profile.wanted_employment_types)}
            />
            <Fact
              label={t('welcome.summary.dream')}
              value={list(profile.dream_employers)}
            />
            <Fact
              label={t('welcome.summary.skip')}
              value={list(profile.excluded_employers)}
            />
            <Fact
              label={t('welcome.summary.sources')}
              value={list(payload?.sources.map((one) => one.source_id))}
            />
            <Fact
              label={t('welcome.summary.freshness')}
              value={t('welcome.summary.days', { count: profile.max_age_days })}
            />
          </dl>
        </Section>
      ) : null}
    </>
  );
}
