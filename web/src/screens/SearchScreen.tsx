/**
 * 01 — Search.
 *
 * Two things carry this screen. The source list draws each source's form from
 * the manifest the server sends, so installing a plugin makes its form appear
 * here without a line being written. And the run, once started, prints its own
 * commentary live -- a search that talks to a dozen strangers' servers takes
 * long enough that silence would read as a hang.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, ApiError } from '@/lib/api';
import { EMPTY_PROFILE, type SearchProfile, type SourceManifest } from '@/lib/types';
import { formatWhen } from '@/lib/format';
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
import SourceCard from '@/components/SourceCard';
import KeywordGroups from '@/components/KeywordGroups';

export default function SearchScreen() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const sources = useQuery({ queryKey: ['sources'], queryFn: api.sources });
  const saved = useQuery({ queryKey: ['profiles', 'search'], queryFn: () => api.profiles('search') });

  const [chosen, setChosen] = useState<Record<string, Record<string, unknown>>>({});
  const [profile, setProfile] = useState<SearchProfile>(EMPTY_PROFILE);
  const [runId, setRunId] = useState<string | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [phase, setPhase] = useState<'idle' | 'running' | 'done' | 'failed' | 'cancelled'>('idle');
  const [saveName, setSaveName] = useState('');
  const logRef = useRef<HTMLDivElement>(null);

  const chosenIds = Object.keys(chosen);

  const start = useMutation({
    mutationFn: () =>
      api.startSearch({
        sources: chosenIds.map((id) => ({ source_id: id, params: chosen[id] ?? {} })),
        profile,
      }),
    onSuccess: (run) => {
      setRunId(run.id);
      setLines([]);
      setPhase('running');
    },
  });

  // The live commentary. Unsubscribing on unmount matters: a user who wanders
  // off to another screen mid-search should not leave a socket behind.
  useEffect(() => {
    if (!runId || phase !== 'running') return;
    return api.watchRun(
      runId,
      (line) => setLines((current) => [...current, line]),
      (ended) => {
        setPhase(ended === 'done' ? 'done' : ended === 'cancelled' ? 'cancelled' : 'failed');
        void queryClient.invalidateQueries({ queryKey: ['postings'] });
        void queryClient.invalidateQueries({ queryKey: ['board'] });
        void queryClient.invalidateQueries({ queryKey: ['sources'] });
      },
    );
  }, [runId, phase, queryClient]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [lines]);

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

  const toggle = (id: string, defaults: Record<string, unknown>) =>
    setChosen((current) => {
      if (id in current) {
        const { [id]: _removed, ...rest } = current;
        return rest;
      }
      return { ...current, [id]: defaults };
    });

  const running = phase === 'running';

  return (
    <>
      <ScreenHeader
        number="01"
        title={t('search.title')}
        lede={t('search.lede')}
        aside={
          <button
            type="button"
            className="btn btn-primary"
            disabled={running || chosenIds.length === 0}
            onClick={() => start.mutate()}
          >
            {running ? t('search.running') : t('search.run')}
          </button>
        }
      />

      {chosenIds.length === 0 && start.isError ? (
        <div className="mt-[var(--gap-wide)]">
          <Note tone="warn">{t('search.noSources')}</Note>
        </div>
      ) : null}

      {start.error instanceof ApiError ? (
        <div className="mt-[var(--gap-wide)]">
          <Problem message={start.error.message} />
        </div>
      ) : null}

      {runId ? (
        <Section
          label={t('search.progress')}
          aside={
            running ? (
              <button
                type="button"
                className="btn btn-quiet"
                onClick={() => void api.cancelRun(runId)}
              >
                {t('search.stop')}
              </button>
            ) : phase === 'done' ? (
              <button
                type="button"
                className="btn btn-quiet"
                onClick={() => navigate('/results')}
              >
                {t('search.seeResults')}
              </button>
            ) : null
          }
        >
          <div
            ref={logRef}
            role="log"
            aria-live="polite"
            className="panel-sunk mono max-h-[15rem] overflow-y-auto px-[var(--gap)] py-[var(--gap-tight)] text-[var(--text-small)] leading-relaxed"
          >
            {lines.length === 0 ? (
              <p className="text-[var(--ink-faint)]">{t('search.waiting')}</p>
            ) : (
              lines.map((line, index) => (
                <p key={index} className="whitespace-pre-wrap">
                  {line}
                </p>
              ))
            )}
            {phase !== 'idle' && phase !== 'running' ? (
              <p
                className="mt-[var(--gap-tight)] font-semibold"
                style={{
                  color: phase === 'done' ? 'var(--ok)' : phase === 'failed' ? 'var(--bad)' : 'var(--warn)',
                }}
              >
                {t(`search.${phase === 'done' ? 'finished' : phase}`)}
              </p>
            ) : null}
          </div>
        </Section>
      ) : null}

      <Section
        label={t('search.sources')}
        aside={
          chosenIds.length ? (
            <span className="eyebrow">{t('search.chosen', { count: chosenIds.length })}</span>
          ) : null
        }
      >
        {sources.isLoading ? <Loading /> : null}
        {sources.error ? <Problem message={String(sources.error)} onRetry={() => void sources.refetch()} /> : null}

        {sources.data ? (
          <>
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
                  onToggle={toggle}
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
                      onToggle={toggle}
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
