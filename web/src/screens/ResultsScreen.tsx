/**
 * 02 — Results.
 *
 * A dense table, because that is what the data is. Rows are tight, the rule
 * lines are hairlines, and the only things given room are the two columns a
 * person actually reads: the position and why it is on the list.
 *
 * Filtering and paging happen on the server. A local `filter()` would be one
 * line shorter and would quietly lie about the total once there were more jobs
 * than one page.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { BOARD_ORDER, type ApplicationStatus, type JobRow } from '@/lib/types';
import { daysUntil, formatDate, hostOf } from '@/lib/format';
import { Empty, Loading, Problem, ScreenHeader } from '@/components/primitives';
import LetterDialog from '@/components/LetterDialog';

const PAGE = 50;

export default function ResultsScreen() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'' | ApplicationStatus>('');
  const [offset, setOffset] = useState(0);
  const [letterFor, setLetterFor] = useState<JobRow | null>(null);

  const page = useQuery({
    queryKey: ['postings', query, status, offset],
    queryFn: () => api.postings({ q: query, status: status || undefined, limit: PAGE, offset }),
    placeholderData: keepPreviousData,
  });

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

  return (
    <>
      <ScreenHeader
        number="02"
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
      </div>

      <div className="mt-[var(--gap-wide)]">
        {page.isLoading ? <Loading /> : null}
        {page.error ? (
          <Problem message={String(page.error)} onRetry={() => void page.refetch()} />
        ) : null}

        {page.data && rows.length === 0 ? (
          <Empty>{query || status ? t('results.noMatch') : t('results.empty')}</Empty>
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
                        <a
                          href={row.posting.url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="font-semibold hover:text-[var(--accent)] hover:underline"
                        >
                          {row.posting.title}
                        </a>
                        <div className="text-[var(--ink-soft)]">{row.posting.company}</div>
                        {row.note ? (
                          <div className="mt-[var(--gap-hair)] text-[var(--text-micro)] leading-snug text-[var(--ink-faint)]">
                            {row.note}
                          </div>
                        ) : null}
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

                      <td className="px-[var(--gap)] py-[var(--gap-tight)]">
                        {/* The select carries the status colour itself rather
                            than sitting next to a badge repeating it: one
                            control, one statement, and it still works from a
                            keyboard. */}
                        <select
                          className="field max-w-[9rem] py-[0.15rem] text-[var(--text-micro)] font-semibold"
                          aria-label={`${t('results.status')} — ${row.posting.title}`}
                          value={row.status}
                          style={{
                            color: `var(--status-${row.status})`,
                            background: `var(--status-${row.status}-soft)`,
                            borderColor: `var(--status-${row.status})`,
                          }}
                          onChange={(event) =>
                            move.mutate({
                              key: row.dedup_key,
                              next: event.target.value as ApplicationStatus,
                            })
                          }
                        >
                          {BOARD_ORDER.map((value) => (
                            <option key={value} value={value}>
                              {t(`status.${value}`)}
                            </option>
                          ))}
                        </select>
                      </td>

                      <td className="whitespace-nowrap px-[var(--gap)] py-[var(--gap-tight)] text-right">
                        <button
                          type="button"
                          className="btn btn-bare"
                          onClick={() => setLetterFor(row)}
                          title={t('results.letter')}
                        >
                          ✎
                        </button>
                        <button
                          type="button"
                          className="btn btn-bare"
                          style={{ color: 'var(--ink-faint)' }}
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

      {letterFor ? (
        <LetterDialog row={letterFor} onClose={() => setLetterFor(null)} />
      ) : null}
    </>
  );
}
