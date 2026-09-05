/**
 * 02 — Results.
 *
 * A dense table, because that is what the data is. Rows are tight, the rule
 * lines are hairlines, and the only things given room are the two columns a
 * person actually reads: the position and why it is on the list.
 *
 * This screen is for sifting, not for managing. An undecided ad gets two
 * answers -- keep it or discard it -- and nothing else. The full set of
 * statuses used to live here as a dropdown on every row, which asked the wrong
 * question at the wrong moment: "have I applied yet?" about an ad nobody has
 * read. Once an ad is kept it becomes the tracker's business, and that is where
 * its status is set.
 *
 * Filtering and paging happen on the server. A local `filter()` would be one
 * line shorter and would quietly lie about the total once there were more jobs
 * than one page.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { BOARD_ORDER, type ApplicationStatus, type JobRow } from '@/lib/types';
import { daysUntil, formatDate, formatWhen, hostOf } from '@/lib/format';
import { Empty, Loading, Problem, ScreenHeader, StatusPill } from '@/components/primitives';
import { screenNumber } from '@/lib/screens';
import JobDetailDialog from '@/components/JobDetailDialog';
import LetterDialog from '@/components/LetterDialog';

const PAGE = 50;

export default function ResultsScreen() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Which search, kept in the address. A run finishes on another screen and
  // sends the user here with `?run=`, and that link has to survive a reload.
  const [params, setParams] = useSearchParams();
  const run = params.get('run') ?? '';

  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'' | ApplicationStatus>('');
  const [offset, setOffset] = useState(0);
  const [letterFor, setLetterFor] = useState<JobRow | null>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);

  /**
   * Ads kept during this visit.
   *
   * Keeping deliberately does not change the status: a kept ad is still `new`,
   * which is exactly what the tracker's first column means. So there is nothing
   * on the server to record it, and the set is local -- it exists to take the
   * two buttons off a row the user has already answered, and to know when the
   * page has been worked through. A reload forgets it, and forgetting is
   * harmless: the ad is still there, still new, still in the tracker.
   */
  const [kept, setKept] = useState<ReadonlySet<string>>(new Set());

  const page = useQuery({
    queryKey: ['postings', query, status, run, offset],
    queryFn: () =>
      api.postings({
        q: query,
        status: status || undefined,
        run: run || undefined,
        limit: PAGE,
        offset,
      }),
    placeholderData: keepPreviousData,
  });

  const searches = useQuery({ queryKey: ['searchRuns'], queryFn: () => api.searchRuns() });

  const move = useMutation({
    mutationFn: ({ key, next }: { key: string; next: ApplicationStatus }) =>
      api.move(key, next),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['postings'] });
      void queryClient.invalidateQueries({ queryKey: ['board'] });
    },
  });

  const forget = useMutation({
    mutationFn: (key: string) => api.forget(key),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['postings'] });
      void queryClient.invalidateQueries({ queryKey: ['board'] });
    },
  });

  const rows = page.data?.rows ?? [];
  const total = page.data?.total ?? 0;
  const open = rows.find((row) => row.dedup_key === openKey) ?? null;

  const undecided = (row: JobRow) => row.status === 'new' && !kept.has(row.dedup_key);
  /** Everything on this page has been answered, so there is somewhere to go next. */
  const sifted = rows.length > 0 && !rows.some(undecided);

  const keep = (key: string) =>
    setKept((current) => new Set(current).add(key));

  const chooseRun = (next: string) => {
    setOffset(0);
    setParams(next ? { run: next } : {}, { replace: true });
  };

  return (
    <>
      <ScreenHeader
        number={screenNumber('results')}
        title={t('results.title')}
        lede={t('results.lede')}
        aside={
          <span className="mono text-[var(--text-small)] text-[var(--ink-faint)]">
            {total}
          </span>
        }
      />

      <div className="mt-[var(--gap-wide)] flex flex-wrap items-center gap-[var(--gap-tight)]">
        <input
          className="field max-w-[22rem]"
          type="search"
          aria-label={t('results.searchPlaceholder')}
          placeholder={t('results.searchPlaceholder')}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOffset(0);
          }}
        />
        <select
          className="field max-w-[12rem]"
          aria-label={t('results.status')}
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as '' | ApplicationStatus);
            setOffset(0);
          }}
        >
          <option value="">{t('results.allStatuses')}</option>
          {BOARD_ORDER.map((value) => (
            <option key={value} value={value}>
              {t(`status.${value}`)}
            </option>
          ))}
        </select>

        {/* Which search brought these in. `found_at` is a date, so two searches
            in one morning cannot be told apart by it -- this is the only thing
            that separates "what I just found" from "everything". */}
        <select
          className="field max-w-[18rem]"
          aria-label={t('results.whichSearch')}
          value={run}
          onChange={(event) => chooseRun(event.target.value)}
        >
          <option value="">{t('results.allSearches')}</option>
          {(searches.data ?? []).map((one, index) => (
            <option key={one.id} value={String(one.id)}>
              {index === 0 ? `${t('results.latestSearch')} — ` : ''}
              {formatWhen(one.started_at, i18n.language)} ·{' '}
              {t('common.jobs', { count: one.added })}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-[var(--gap-wide)]">
        {page.isLoading ? <Loading /> : null}
        {page.error ? (
          <Problem message={String(page.error)} onRetry={() => void page.refetch()} />
        ) : null}

        {page.data && rows.length === 0 ? (
          <Empty>{query || status || run ? t('results.noMatch') : t('results.empty')}</Empty>
        ) : null}

        {rows.length ? (
          <div className="panel scroll-x">
            <table className="w-full border-collapse text-[var(--text-small)]">
              <thead>
                <tr className="rule-b bg-[var(--ground-sunk)] text-left">
                  <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)]">
                    {t('results.found')}
                  </th>
                  <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)]">
                    {t('results.position')}
                  </th>
                  <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)]">
                    {t('results.source')}
                  </th>
                  <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)]">
                    {t('results.place')}
                  </th>
                  <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)]">
                    {t('results.closes')}
                  </th>
                  <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)]">
                    {t('results.status')}
                  </th>
                  <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)] text-right">
                    <span className="sr-only">{t('common.open')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const closing = daysUntil(row.posting.deadline);
                  return (
                    <tr
                      key={row.dedup_key}
                      className="rule-b align-top transition-colors last:border-b-0 hover:bg-[var(--surface-raised)]"
                    >
                      <td className="mono whitespace-nowrap px-[var(--gap)] py-[var(--gap-tight)] text-[var(--text-micro)] text-[var(--ink-faint)]">
                        {formatDate(row.found_at, i18n.language)}
                      </td>

                      <td className="max-w-[34rem] px-[var(--gap)] py-[var(--gap-tight)]">
                        {/* Opens the same detail dialog Tracking uses, rather
                            than leaving straight for the original ad -- the
                            status, the letter and the real "open ad" link now
                            live in one place instead of two. */}
                        <button
                          type="button"
                          className="text-left font-semibold hover:text-[var(--accent)] hover:underline"
                          onClick={() => setOpenKey(row.dedup_key)}
                        >
                          {row.posting.title}
                        </button>
                        <div className="text-[var(--ink-soft)]">{row.posting.company}</div>
                        {row.note ? (
                          <div className="mt-[var(--gap-hair)] text-[var(--text-micro)] leading-snug text-[var(--ink-faint)]">
                            {row.note}
                          </div>
                        ) : null}
                      </td>

                      {/* Which source found it. The only trace of this before
                          was the domain under "Place", which is a different
                          question and often a different answer. */}
                      <td className="whitespace-nowrap px-[var(--gap)] py-[var(--gap-tight)]">
                        <span className="mono text-[var(--text-micro)] text-[var(--ink-soft)]">
                          {row.posting.source_id}
                        </span>
                      </td>

                      <td className="px-[var(--gap)] py-[var(--gap-tight)] text-[var(--ink-soft)]">
                        {row.posting.location}
                        <div className="mono text-[var(--text-micro)] text-[var(--ink-faint)]">
                          {hostOf(row.posting.url)}
                        </div>
                      </td>

                      <td
                        className="mono whitespace-nowrap px-[var(--gap)] py-[var(--gap-tight)] text-[var(--text-micro)]"
                        style={{
                          color:
                            closing !== null && closing <= 3
                              ? 'var(--bad)'
                              : closing !== null && closing <= 7
                                ? 'var(--warn)'
                                : 'var(--ink-faint)',
                        }}
                      >
                        {formatDate(row.posting.deadline, i18n.language)}
                      </td>

                      {/* Two answers while it is undecided, a plain statement of
                          fact once it is not. Setting the status is the
                          tracker's job from here on. */}
                      <td className="whitespace-nowrap px-[var(--gap)] py-[var(--gap-tight)]">
                        {undecided(row) ? (
                          <div className="flex flex-wrap gap-[var(--gap-hair)]">
                            <button
                              type="button"
                              className="btn btn-quiet px-[var(--gap-tight)] py-[0.15rem] text-[var(--text-micro)]"
                              style={{ color: 'var(--ok)', borderColor: 'var(--ok)' }}
                              aria-label={`${t('results.keep')} — ${row.posting.title}`}
                              onClick={() => keep(row.dedup_key)}
                            >
                              {t('results.keep')}
                            </button>
                            <button
                              type="button"
                              className="btn btn-quiet px-[var(--gap-tight)] py-[0.15rem] text-[var(--text-micro)]"
                              style={{ color: 'var(--ink-faint)' }}
                              aria-label={`${t('results.discard')} — ${row.posting.title}`}
                              onClick={() =>
                                move.mutate({ key: row.dedup_key, next: 'skipped' })
                              }
                            >
                              {t('results.discard')}
                            </button>
                          </div>
                        ) : (
                          <StatusPill status={row.status} />
                        )}
                      </td>

                      <td className="whitespace-nowrap px-[var(--gap)] py-[var(--gap-tight)] text-right">
                        {/* Writing a letter now happens from the detail
                            dialog (open it via the title), alongside the
                            real "open ad" link and the status -- not as a
                            second, disconnected action on the row. */}
                        <button
                          type="button"
                          className="btn btn-bare"
                          style={{ color: 'var(--ink-faint)' }}
                          aria-label={`${t('results.forget')} — ${row.posting.title}`}
                          title={t('results.forget')}
                          onClick={() => {
                            if (window.confirm(t('results.forgetSure'))) {
                              forget.mutate(row.dedup_key);
                            }
                          }}
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        {/* Nothing undecided left on this page. Say where to go next rather
            than leaving the user on a screen with nothing left to do on it. */}
        {sifted ? (
          <div className="mt-[var(--gap)] flex justify-end">
            <button
              type="button"
              className="btn btn-primary py-[var(--gap-tight)]"
              onClick={() => navigate('/tracker')}
            >
              {t('results.continueToTracker')} →
            </button>
          </div>
        ) : null}

        {total > PAGE ? (
          <div className="mt-[var(--gap)] flex items-center justify-between">
            <button
              type="button"
              className="btn btn-quiet"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              ← {t('results.previous')}
            </button>
            <span className="mono text-[var(--text-micro)] text-[var(--ink-faint)]">
              {t('results.showing', {
                from: offset + 1,
                to: Math.min(offset + PAGE, total),
                total,
              })}
            </span>
            <button
              type="button"
              className="btn btn-quiet"
              disabled={offset + PAGE >= total}
              onClick={() => setOffset(offset + PAGE)}
            >
              {t('results.next')} →
            </button>
          </div>
        ) : null}
      </div>

      {open ? (
        <JobDetailDialog
          row={open}
          order={BOARD_ORDER}
          onClose={() => setOpenKey(null)}
          onMove={(next) => move.mutate({ key: open.dedup_key, next })}
          onDiscard={
            open.status === 'skipped'
              ? undefined
              : () => move.mutate({ key: open.dedup_key, next: 'skipped' })
          }
          onWriteLetter={() => {
            setLetterFor(open);
            setOpenKey(null);
          }}
        />
      ) : null}

      {letterFor ? (
        <LetterDialog row={letterFor} onClose={() => setLetterFor(null)} />
      ) : null}
    </>
  );
}
