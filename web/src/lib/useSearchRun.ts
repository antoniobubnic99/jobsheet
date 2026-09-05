/**
 * One search in flight, and everything a screen needs to show it.
 *
 * This lives outside both screens because two of them start searches: the home
 * screen, from the setup the wizard saved, and the editor, from whatever is
 * currently in the form. The commentary, the bars and the ending are identical
 * in both places, and a second copy of this would be a second place for the
 * unsubscribe to be forgotten.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { api, ApiError } from './api';
import type { SearchProfile, SourceChoice, SourceProgress } from './types';

export type RunState = 'idle' | 'running' | 'done' | 'failed' | 'cancelled';

export interface SearchRun {
  state: RunState;
  /** The in-memory run id, for cancelling and for the stream. */
  runId: string | null;
  /** The `runs` row it became, once finished. Empty until then. */
  recordedId: string;
  lines: string[];
  /** One entry per source, in the order the server first mentioned them. */
  progress: SourceProgress[];
  found: number;
  error: string;
  /** Why a given source failed, keyed by source id -- the reason `SourceBar`
      shows next to a red bar instead of leaving it unexplained. */
  errors: Record<string, string>;
  start: (sources: SourceChoice[], profile: SearchProfile) => void;
  cancel: () => void;
}

export function useSearchRun(): SearchRun {
  const queryClient = useQueryClient();

  const [runId, setRunId] = useState<string | null>(null);
  const [recordedId, setRecordedId] = useState('');
  const [state, setState] = useState<RunState>('idle');
  const [lines, setLines] = useState<string[]>([]);
  const [progress, setProgress] = useState<SourceProgress[]>([]);
  const [found, setFound] = useState(0);
  const [error, setError] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  // The id the effect below is allowed to act on. Without it, a second search
  // started while the first is still closing down can have its results
  // overwritten by the first one's ending.
  const current = useRef<string | null>(null);

  const start = useCallback(
    (sources: SourceChoice[], profile: SearchProfile) => {
      setLines([]);
      setProgress([]);
      setFound(0);
      setError('');
      setErrors({});
      setRecordedId('');
      setState('running');
      api
        .startSearch({
          sources: sources.map((one) => ({
            source_id: one.source_id,
            params: one.params ?? {},
          })),
          profile,
        })
        .then((run) => {
          current.current = run.id;
          setRunId(run.id);
        })
        .catch((problem: unknown) => {
          setState('failed');
          setError(problem instanceof ApiError ? problem.message : String(problem));
        });
    },
    [],
  );

  const cancel = useCallback(() => {
    if (runId) void api.cancelRun(runId);
  }, [runId]);

  useEffect(() => {
    if (!runId || state !== 'running') return;

    return api.watchRun(
      runId,
      (line) => setLines((all) => [...all, line]),
      (ended) => {
        if (current.current !== runId) return;
        setState(ended === 'done' ? 'done' : ended === 'cancelled' ? 'cancelled' : 'failed');

        // What the run actually produced. The stream says how it ended, not how
        // much it found, and the big button has to name a number.
        void api
          .run(runId)
          .then((summary) => {
            setFound(summary.new);
            setRecordedId(summary.run_id);
            if (summary.error) setError(summary.error);
            setErrors(summary.errors ?? {});
          })
          .catch(() => undefined);

        void queryClient.invalidateQueries({ queryKey: ['postings'] });
        void queryClient.invalidateQueries({ queryKey: ['board'] });
        void queryClient.invalidateQueries({ queryKey: ['sources'] });
        void queryClient.invalidateQueries({ queryKey: ['searchRuns'] });
      },
      (one) =>
        setProgress((all) => {
          const at = all.findIndex((entry) => entry.source_id === one.source_id);
          if (at === -1) return [...all, one];
          const next = [...all];
          next[at] = one;
          return next;
        }),
    );
  }, [runId, state, queryClient]);

  return { state, runId, recordedId, lines, progress, found, error, errors, start, cancel };
}
