/**
 * Edit the search — reached from the home screen, not from the rail.
 *
 * Two things carry this screen. The source list draws each source's form from
 * the manifest the server sends, so installing a plugin makes its form appear
 * here without a line being written. And the run, once started, reports itself
 * live -- a search that talks to a dozen strangers' servers takes long enough
 * that silence would read as a hang.
 *
 * It opens filled in. The wizard that runs once after signing up writes the
 * account's setup, and this screen reads it back, so the first thing somebody
 * sees here is their own search rather than the blank form the wizard exists to
 * spare them. Seeding happens once, and only into untouched state: a setup
 * arriving late must never overwrite something being typed.
 *
 * This used to be the front page. It is a form with six sections, which is the
 * right shape for changing a search and the wrong shape for running one, so the
 * daily action moved to `HomeScreen` and this became the place you come to when
 * something needs adjusting.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { api, ApiError, DEFAULT_SETUP } from '@/lib/api';
import {
  EMPTY_PROFILE,
  type SearchProfile,
  type SearchSetup,
  type SourceManifest,
} from '@/lib/types';
import { screenNumber } from '@/lib/screens';
import { useSearchRun } from '@/lib/useSearchRun';
import { formatWhen } from '@/lib/format';
import { deriveCountyFeeds, deriveSourceParams } from '@/lib/sourceDefaults';
import {
  ChipInput,
  Empty,
  Labelled,
  Loading,
  Note,
  Problem,
  ScreenHeader,
  Section,
} from '@/components/primitives';
import RunProgress from '@/components/RunProgress';
import SourceBulkActions from '@/components/SourceBulkActions';
import SourceCard from '@/components/SourceCard';
import KeywordGroups from '@/components/KeywordGroups';

export default function SearchScreen() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const sources = useQuery({ queryKey: ['sources'], queryFn: api.sources });
  const saved = useQuery({ queryKey: ['profiles', 'search'], queryFn: () => api.profiles('search') });

  // The employment-service feeds implied by the counties named in "Gdje" --
  // the same mapping the wizard uses, so a source ticked here starts from the
  // same answer instead of asking the user to name their county twice.
  const counties = useQuery({
    queryKey: ['places', 'county'],
    queryFn: () => api.places('', 'county'),
    staleTime: Infinity,
  });

  // The wizard's answers. A 404 is the ordinary state for an account that
  // predates the wizard, so it is an absence rather than an error.
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

  const [chosen, setChosen] = useState<Record<string, Record<string, unknown>>>({});
  const [profile, setProfile] = useState<SearchProfile>(EMPTY_PROFILE);
  const [seeded, setSeeded] = useState(false);
  const [saveName, setSaveName] = useState('');

  const run = useSearchRun();
  const chosenIds = Object.keys(chosen);

  const startHere = () =>
    run.start(
      chosenIds.map((id) => ({ source_id: id, params: chosen[id] ?? {} })),
      profile,
    );

  useEffect(() => {
    const payload = setup.data?.payload;
    if (seeded || !payload) return;
    setSeeded(true);
    setProfile({ ...EMPTY_PROFILE, ...payload.profile });
    setChosen(
      Object.fromEntries(payload.sources.map((one) => [one.source_id, one.params])),
    );
  }, [seeded, setup.data]);

  const grouped = useMemo(() => {
    const all = sources.data?.sources ?? [];
    const global = all.filter((source) => source.is_global);
    const byCountry = new Map<string, SourceManifest[]>();
    for (const source of all) {
      if (source.is_global) continue;
      const list = byCountry.get(source.country ?? '') ?? [];
      list.push(source);
      byCountry.set(source.country ?? '', list);
    }
    return { global, byCountry };
  }, [sources.data]);

  const countyFeeds = useMemo(
    () => deriveCountyFeeds(profile.regions, counties.data?.counties ?? []),
    [counties.data, profile.regions],
  );

  const toggle = (id: string, defaults: Record<string, unknown>) =>
    setChosen((current) => {
      if (id in current) {
        const { [id]: _removed, ...rest } = current;
        return rest;
      }
      return { ...current, [id]: defaults };
    });

  /** Tick exactly this set, keeping the parameters of anything already ticked. */
  const choose = (wanted: SourceManifest[]) =>
    setChosen((current) =>
      Object.fromEntries(
        wanted.map((source) => [
          source.id,
          current[source.id] ?? deriveSourceParams(source, profile, countyFeeds),
        ]),
      ),
    );

  const running = run.state === 'running';

  return (
    <>
      <ScreenHeader
        number={screenNumber('searchEdit')}
        title={t('search.title')}
        lede={t('search.lede')}
        aside={
          <button
            type="button"
            className="btn btn-primary"
            disabled={running || chosenIds.length === 0}
            onClick={startHere}
          >
            {running ? t('search.running') : t('search.run')}
          </button>
        }
      />

      {chosenIds.length === 0 ? (
        <div className="mt-[var(--gap-wide)]">
          <Note tone="warn">{t('search.noSources')}</Note>
        </div>
      ) : null}

      {run.state !== 'idle' ? (
        <RunProgress
          state={run.state}
          progress={run.progress}
          lines={run.lines}
          found={run.found}
          error={run.error}
          onStop={run.cancel}
          onRetry={startHere}
          onSeeResults={() =>
            navigate(run.recordedId ? `/results?run=${run.recordedId}` : '/results')
          }
        />
      ) : null}

      <Section label={t('search.sources')}>
        {sources.isLoading ? <Loading /> : null}
        {sources.error ? <Problem message={String(sources.error)} onRetry={() => void sources.refetch()} /> : null}

        {sources.data ? (
          <>
            <SourceBulkActions
              sources={sources.data.sources}
              countries={[...grouped.byCountry.keys()]}
              chosenCount={chosenIds.length}
              onChoose={choose}
            />

            <h3 className="eyebrow mb-[var(--gap-tight)] mt-[var(--gap-tight)]">
              {t('search.global')}
            </h3>
            <div className="grid gap-[var(--gap-tight)] sm:grid-cols-2 xl:grid-cols-3">
              {grouped.global.map((source) => (
                <SourceCard
                  key={source.id}
                  source={source}
                  chosen={source.id in chosen}
                  params={chosen[source.id] ?? {}}
                  onToggle={(id) => toggle(id, deriveSourceParams(source, profile, countyFeeds))}
                  onParams={(id, params) =>
                    setChosen((current) => ({ ...current, [id]: params }))
                  }
                  locale={i18n.language}
                />
              ))}
            </div>

            {[...grouped.byCountry.entries()].map(([country, list]) => (
              <div key={country} className="mt-[var(--gap-wide)]">
                <h3 className="eyebrow mb-[var(--gap-tight)]">
                  {t('search.byCountry')} · <span className="mono">{country}</span>
                </h3>
                <div className="grid gap-[var(--gap-tight)] sm:grid-cols-2 xl:grid-cols-3">
                  {list.map((source) => (
                    <SourceCard
                      key={source.id}
                      source={source}
                      chosen={source.id in chosen}
                      params={chosen[source.id] ?? {}}
                      onToggle={(id) =>
                        toggle(id, deriveSourceParams(source, profile, countyFeeds))
                      }
                      onParams={(id, params) =>
                        setChosen((current) => ({ ...current, [id]: params }))
                      }
                      locale={i18n.language}
                    />
                  ))}
                </div>
              </div>
            ))}
          </>
        ) : null}
      </Section>

      <Section label={t('search.keywords')} hint={t('search.keywordsHelp')}>
        <KeywordGroups
          groups={profile.keyword_groups}
          onChange={(keyword_groups) => setProfile({ ...profile, keyword_groups })}
        />
      </Section>

      <Section label={t('search.where')}>
        <div className="grid gap-[var(--gap)] md:grid-cols-2">
          <Labelled label={t('search.locations')} hint={t('search.locationHelp')}>
            <ChipInput
              ariaLabel={t('search.locations')}
              values={profile.locations}
              placeholder={t('search.locationPlaceholder')}
              onChange={(locations) => setProfile({ ...profile, locations })}
            />
          </Labelled>
          <Labelled label={t('search.maxAge')}>
            <div className="flex items-center gap-[var(--gap-tight)]">
              <input
                type="number"
                min={1}
                max={365}
                className="field tabular max-w-[7rem]"
                value={profile.max_age_days}
                onChange={(event) =>
                  setProfile({ ...profile, max_age_days: Number(event.target.value) || 30 })
                }
              />
              <span className="text-[var(--text-small)] text-[var(--ink-soft)]">
                {t('search.days')}
              </span>
            </div>
          </Labelled>
        </div>
      </Section>

      <Section label={t('search.filters')}>
        <div className="grid gap-[var(--gap)] md:grid-cols-2">
          <Labelled label={t('search.excludeEmployers')}>
            <ChipInput
              ariaLabel={t('search.excludeEmployers')}
              values={profile.excluded_employers}
              onChange={(excluded_employers) => setProfile({ ...profile, excluded_employers })}
            />
          </Labelled>
          <Labelled label={t('search.excludeTypes')}>
            <ChipInput
              ariaLabel={t('search.excludeTypes')}
              values={profile.excluded_employment_types}
              onChange={(excluded_employment_types) =>
                setProfile({ ...profile, excluded_employment_types })
              }
            />
          </Labelled>
        </div>
      </Section>

      <Section label={t('search.savedSearches')}>
        <div className="flex flex-wrap items-end gap-[var(--gap-tight)]">
          <input
            className="field max-w-[16rem]"
            placeholder={t('search.namePlaceholder')}
            value={saveName}
            aria-label={t('search.saveAs')}
            onChange={(event) => setSaveName(event.target.value)}
          />
          <button
            type="button"
            className="btn btn-quiet"
            disabled={!saveName.trim()}
            onClick={async () => {
              await api.saveProfile('search', saveName.trim(), profile);
              setSaveName('');
              void queryClient.invalidateQueries({ queryKey: ['profiles', 'search'] });
            }}
          >
            {t('search.saveAs')}
          </button>
        </div>

        <div className="mt-[var(--gap)] flex flex-wrap gap-[var(--gap-hair)]">
          {saved.data?.length ? (
            saved.data.map((name) => (
              <span key={name} className="panel flex items-center gap-[var(--gap-hair)] px-[var(--gap-tight)] py-[0.15rem]">
                <button
                  type="button"
                  className="text-[var(--text-small)] hover:text-[var(--accent)]"
                  onClick={async () => {
                    const loaded = await api.loadProfile<SearchProfile>('search', name);
                    setProfile({ ...EMPTY_PROFILE, ...loaded.payload });
                  }}
                >
                  {name}
                </button>
                <button
                  type="button"
                  className="text-[var(--ink-faint)] hover:text-[var(--bad)]"
                  aria-label={`${t('common.delete')} ${name}`}
                  onClick={async () => {
                    await api.deleteProfile('search', name);
                    void queryClient.invalidateQueries({ queryKey: ['profiles', 'search'] });
                  }}
                >
                  ×
                </button>
              </span>
            ))
          ) : (
            <Empty>{t('common.nothing')}</Empty>
          )}
        </div>

        {saved.dataUpdatedAt ? (
          <p className="mt-[var(--gap-tight)] text-[var(--text-micro)] text-[var(--ink-faint)]">
            {formatWhen(new Date(saved.dataUpdatedAt).toISOString(), i18n.language)}
          </p>
        ) : null}
      </Section>
    </>
  );
}
