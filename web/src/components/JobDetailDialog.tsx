/**
 * One posting, everything you can do about it, and how it got there.
 *
 * Results and Tracker both need to show a posting's status, open the real ad
 * and start a cover letter, so both open this dialog instead of each keeping
 * their own copy of it. It owns its own history fetch, so neither screen has
 * to wire that plumbing just to open one.
 *
 * The status controls and the actions that follow from them sit in one boxed
 * group -- "where things stand" and "what you can do about it" read as a
 * single decision, not two rows that happen to be near each other.
 */

import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import type { ApplicationStatus, JobRow } from '@/lib/types';
import { formatWhen } from '@/lib/format';
import { Dialog, StatusPill } from '@/components/primitives';

/** Keep a pointer gesture from reaching whatever is underneath it -- the
    tracker board uses this on a card that is otherwise a drag handle. */
const KEEP_TO_ITSELF = {
  onPointerDown: (event: React.PointerEvent) => event.stopPropagation(),
  onClick: (event: React.MouseEvent) => event.stopPropagation(),
};

export function StatusSelect({
  row,
  order,
  onMove,
  className = '',
}: {
  row: JobRow;
  order: ApplicationStatus[];
  onMove: (next: ApplicationStatus) => void;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <select
      className={`field w-auto ${className}`}
      aria-label={`${t('results.status')} — ${row.posting.title}`}
      value={row.status}
      {...KEEP_TO_ITSELF}
      onChange={(event) => onMove(event.target.value as ApplicationStatus)}
    >
      {order.map((value) => (
        <option key={value} value={value}>
          {t(`status.${value}`)}
        </option>
      ))}
    </select>
  );
}

export default function JobDetailDialog({
  row,
  order,
  onClose,
  onMove,
  onDiscard,
  onWriteLetter,
}: {
  row: JobRow;
  order: ApplicationStatus[];
  onClose: () => void;
  onMove: (next: ApplicationStatus) => void;
  /** Omitted to hide the discard action entirely -- a row that is already
      discarded has nothing left to discard from here. */
  onDiscard?: () => void;
  onWriteLetter: () => void;
}) {
  const { t, i18n } = useTranslation();
  const history = useQuery({
    queryKey: ['history', row.dedup_key],
    queryFn: () => api.history(row.dedup_key),
  });

  return (
    <Dialog title={row.posting.title} onClose={onClose}>
      <p className="text-[var(--text-small)] text-[var(--ink-soft)]">
        {row.posting.company}
        {row.posting.location ? ` · ${row.posting.location}` : ''}
      </p>

      <div className="panel-sunk mt-[var(--gap)] flex flex-col gap-[var(--gap-tight)] p-[var(--gap)]">
        <div className="flex flex-wrap items-center gap-[var(--gap-tight)]">
          <StatusPill status={row.status} />
          <StatusSelect row={row} order={order} onMove={onMove} className="text-[var(--text-small)]" />
        </div>

        <div className="flex flex-wrap items-center gap-[var(--gap-tight)]">
          <a
            href={row.posting.url}
            target="_blank"
            rel="noreferrer noopener"
            className="btn btn-quiet"
          >
            {t('results.openAd')} ↗
          </a>
          <button type="button" className="btn btn-quiet" onClick={onWriteLetter}>
            {t('results.letter')}
          </button>
          {onDiscard ? (
            <button
              type="button"
              className="btn btn-bare text-[var(--ink-faint)] hover:text-[var(--bad)]"
              onClick={onDiscard}
            >
              {t('tracker.discard')}
            </button>
          ) : null}
        </div>
      </div>

      {row.note ? (
        <p className="panel-sunk mt-[var(--gap)] px-[var(--gap)] py-[var(--gap-tight)] text-[var(--text-small)]">
          {row.note}
        </p>
      ) : null}

      <h3 className="rule-t eyebrow mt-[var(--gap-wide)] pt-[var(--gap-wide)]">
        {t('tracker.history')}
      </h3>
      {history.data?.length ? (
        <ol className="mt-[var(--gap-tight)] grid gap-[var(--gap-hair)]">
          {history.data.map((step, index) => (
            <li
              key={index}
              className="rule-b flex items-baseline justify-between gap-[var(--gap)] py-[var(--gap-hair)] last:border-b-0"
            >
              <span className="text-[var(--text-small)]">
                {t('tracker.moved', {
                  from: t(`status.${step.from_status}`),
                  to: t(`status.${step.to_status}`),
                })}
                {step.note ? (
                  <span className="block text-[var(--text-micro)] text-[var(--ink-faint)]">
                    {step.note}
                  </span>
                ) : null}
              </span>
              <span className="mono whitespace-nowrap text-[var(--text-micro)] text-[var(--ink-faint)]">
                {formatWhen(step.at, i18n.language)}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-[var(--gap-tight)] text-[var(--text-small)] text-[var(--ink-faint)]">
          {t('tracker.noHistory')}
        </p>
      )}
    </Dialog>
  );
}
