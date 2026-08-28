/**
 * A search, while it happens.
 *
 * The old version of this printed the raw commentary into a mono box and left
 * the user to read it. That is the right thing to have, and the wrong thing to
 * lead with: the question during a search is "how much longer", and a wall of
 * scrolling text does not answer it.
 *
 * So the bars come first -- one line per source, a name, a rule and a
 * percentage -- and the commentary moves behind a disclosure for the times when
 * something has gone wrong and the detail is the point.
 */

import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import type { SourceProgress } from '@/lib/types';
import type { RunState } from '@/lib/useSearchRun';
import { Section } from '@/components/primitives';

/** Bars are drawn from the server's percentage; this is only their colour. */
function toneOf(phase: SourceProgress['phase']): string {
  if (phase === 'failed') return 'var(--bad)';
  if (phase === 'done') return 'var(--ok)';
  return 'var(--accent)';
}

function SourceBar({ entry }: { entry: SourceProgress }) {
  const { t } = useTranslation();
  const tone = toneOf(entry.phase);

  return (
    <li className="flex items-center gap-[var(--gap)] py-[var(--gap-hair)]">
      <span className="min-w-[9rem] shrink-0 truncate text-[var(--text-small)] font-semibold">
        {entry.source_id}
      </span>

      <span
        className="h-[0.5rem] flex-1 overflow-hidden rounded-[var(--radius-round)] bg-[var(--ground-sunk)]"
        role="progressbar"
        aria-valuenow={entry.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${entry.source_id} — ${t(`search.phase.${entry.phase}`)}`}
      >
        <span
          className="block h-full rounded-[var(--radius-round)] transition-[width] duration-500 ease-out"
          style={{ width: `${entry.percent}%`, background: tone }}
        />
      </span>

      <span
        className="mono w-[3.5rem] shrink-0 text-right text-[var(--text-micro)] tabular-nums"
        style={{ color: tone }}
      >
        {entry.percent}%
      </span>

      <span className="hidden w-[7rem] shrink-0 text-[var(--text-micro)] text-[var(--ink-faint)] sm:block">
        {t(`search.phase.${entry.phase}`)}
      </span>
    </li>
  );
}

export default function RunProgress({
  state,
  progress,
  lines,
  found,
  error,
  onStop,
  onSeeResults,
  onRetry,
}: {
  state: RunState;
  progress: SourceProgress[];
  lines: string[];
  found: number;
  error: string;
  onStop: () => void;
  onSeeResults: () => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [lines]);

  const running = state === 'running';
  const ended = state === 'failed' || state === 'cancelled';

  return (
    <Section
      label={t('search.progress')}
      aside={
        running ? (
          <button type="button" className="btn btn-quiet" onClick={onStop}>
            {t('search.stop')}
          </button>
        ) : null
      }
    >
      {progress.length ? (
        <ul className="panel px-[var(--gap)] py-[var(--gap-tight)]">
          {progress.map((entry) => (
            <SourceBar key={entry.source_id} entry={entry} />
          ))}
        </ul>
      ) : (
        <p className="panel-sunk px-[var(--gap)] py-[var(--gap)] text-[var(--text-small)] text-[var(--ink-faint)]">
          {t('search.waiting')}
        </p>
      )}

      {/* The way out, and there is always one. A search that fell over used to
          leave the screen with no button at all, which left the user stuck on
          a page that had stopped doing anything. */}
      {state === 'done' ? (
        <button
          type="button"
          className="btn btn-primary mt-[var(--gap)] w-full justify-center py-[var(--gap-tight)]"
          onClick={onSeeResults}
        >
          {t('search.seeResultsCount', { count: found })}
        </button>
      ) : null}

      {ended ? (
        <div className="mt-[var(--gap)] flex flex-wrap gap-[var(--gap-tight)]">
          <button
            type="button"
            className="btn btn-primary flex-1 justify-center py-[var(--gap-tight)]"
            onClick={onRetry}
          >
            {t('common.retry')}
          </button>
          <button
            type="button"
            className="btn btn-quiet flex-1 justify-center py-[var(--gap-tight)]"
            onClick={onSeeResults}
          >
            {t('search.seeWhatArrived')}
          </button>
        </div>
      ) : null}

      {state !== 'idle' && state !== 'running' ? (
        <p
          className="mt-[var(--gap-tight)] text-[var(--text-small)] font-semibold"
          style={{
            color:
              state === 'done'
                ? 'var(--ok)'
                : state === 'failed'
                  ? 'var(--bad)'
                  : 'var(--warn)',
          }}
        >
          {t(`search.${state === 'done' ? 'finished' : state}`)}
          {error ? ` — ${error}` : ''}
        </p>
      ) : null}

      {/* Kept, but not in the way. Nobody reads this until something is wrong,
          and then it is the only thing worth reading. */}
      <details className="mt-[var(--gap)]">
        <summary className="eyebrow cursor-pointer select-none text-[var(--ink-faint)] hover:text-[var(--accent)]">
          {t('search.showDetails')}
        </summary>
        <div
          ref={logRef}
          role="log"
          aria-live="polite"
          className="panel-sunk mono mt-[var(--gap-tight)] max-h-[15rem] overflow-y-auto px-[var(--gap)] py-[var(--gap-tight)] text-[var(--text-small)] leading-relaxed"
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
        </div>
      </details>
    </Section>
  );
}
