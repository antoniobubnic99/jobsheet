/**
 * 04 — Tracker.
 *
 * A board, with one design decision worth naming: `Skipped` sits at the far end
 * rather than beside `Rejected`. "I decided against it" and "they decided
 * against me" are different stories, and a board that files them together loses
 * something the person looking at it cares about.
 *
 * Dragging is the obvious interaction, so it is supported -- and so is a plain
 * select on every card, because a board that can only be operated by dragging
 * is closed to anyone using a keyboard.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  DndContext,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { BOARD_ORDER, type ApplicationStatus, type JobRow } from '@/lib/types';
import { formatDate, formatWhen } from '@/lib/format';
import {
  Dialog,
  Empty,
  Loading,
  Problem,
  ScreenHeader,
  StatusPill,
} from '@/components/primitives';

function Card({
  row,
  onOpen,
  onMove,
  locale,
}: {
  row: JobRow;
  onOpen: () => void;
  onMove: (next: ApplicationStatus) => void;
  locale: string;
}) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: row.dedup_key,
  });

  return (
    <article
      ref={setNodeRef}
      style={{
        transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
        opacity: isDragging ? 0.5 : 1,
        zIndex: isDragging ? 30 : undefined,
        position: 'relative',
      }}
      className="panel grid gap-[var(--gap-hair)] p-[var(--gap-tight)]"
    >
      <div className="flex items-start gap-[var(--gap-hair)]">
        <button
          type="button"
          className="btn btn-bare cursor-grab px-[0.2rem] text-[var(--ink-faint)] active:cursor-grabbing"
          aria-label={`Drag ${row.posting.title}`}
          {...attributes}
          {...listeners}
        >
          ⠿
        </button>
        <button
          type="button"
          className="min-w-0 flex-1 text-left text-[var(--text-small)] font-semibold leading-snug hover:text-[var(--accent)]"
          onClick={onOpen}
        >
          {row.posting.title}
        </button>
      </div>

      <p className="pl-[1.4rem] text-[var(--text-micro)] text-[var(--ink-soft)]">
        {row.posting.company}
        {row.posting.location ? ` · ${row.posting.location}` : ''}
      </p>

      <div className="flex items-center justify-between gap-[var(--gap-hair)] pl-[1.4rem]">
        <span className="mono text-[var(--text-micro)] text-[var(--ink-faint)]">
          {formatDate(row.found_at, locale)}
        </span>
        <select
          className="field w-auto py-[0.05rem] text-[var(--text-micro)]"
          aria-label={`${t('results.status')} — ${row.posting.title}`}
          value={row.status}
          onChange={(event) => onMove(event.target.value as ApplicationStatus)}
        >
          {BOARD_ORDER.map((value) => (
            <option key={value} value={value}>
              {t(`status.${value}`)}
            </option>
          ))}
        </select>
      </div>
    </article>
  );
}

function Column({
  status,
  rows,
  children,
}: {
  status: ApplicationStatus;
  rows: JobRow[];
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({ id: status });

  return (
    <section
      ref={setNodeRef}
      className="flex min-w-[12.5rem] flex-1 flex-col rounded-[var(--radius)] transition-colors"
      style={{
        background: isOver ? `var(--status-${status}-soft)` : 'var(--ground-sunk)',
        outline: isOver ? `1px dashed var(--status-${status})` : '1px solid var(--rule)',
      }}
    >
      <header
        className="rule-b flex items-center justify-between px-[var(--gap-tight)] py-[var(--gap-tight)]"
        style={{ borderBottomColor: `var(--status-${status})` }}
      >
        <StatusPill status={status} />
        <span className="mono text-[var(--text-micro)] text-[var(--ink-faint)]">
          {rows.length}
        </span>
      </header>

      <div className="grid flex-1 content-start gap-[var(--gap-tight)] p-[var(--gap-tight)]">
        {rows.length === 0 ? (
          <p className="py-[var(--gap-wide)] text-center text-[var(--text-micro)] text-[var(--ink-faint)]">
            {isOver ? t('tracker.dropHere') : t('tracker.empty')}
          </p>
        ) : (
          children
        )}
      </div>
    </section>
  );
}

export default function TrackerScreen() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<JobRow | null>(null);

  const board = useQuery({ queryKey: ['board'], queryFn: api.board });
  const history = useQuery({
    queryKey: ['history', open?.dedup_key],
    queryFn: () => api.history(open!.dedup_key),
    enabled: Boolean(open),
  });

  const move = useMutation({
    mutationFn: ({ key, next }: { key: string; next: ApplicationStatus }) => api.move(key, next),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['board'] });
      void queryClient.invalidateQueries({ queryKey: ['postings'] });
      void queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const onDragEnd = (event: DragEndEvent) => {
    const next = event.over?.id as ApplicationStatus | undefined;
    if (!next) return;
    move.mutate({ key: String(event.active.id), next });
  };

  if (board.isLoading) return <Loading />;
  if (board.error) {
    return <Problem message={String(board.error)} onRetry={() => void board.refetch()} />;
  }

  const columns = board.data?.columns;
  const anything = Object.values(columns ?? {}).some((rows) => rows.length > 0);

  return (
    <>
      <ScreenHeader number="04" title={t('tracker.title')} lede={t('tracker.lede')} />

      {!anything ? (
        <div className="mt-[var(--gap-wide)]">
          <Empty>{t('results.empty')}</Empty>
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragEnd={onDragEnd}>
          {/* Plain `overflow-x`, not `.scroll-x`: paint containment would clip a
              card the moment it was dragged past the edge of the board. */}
          <div className="mt-[var(--gap-wide)] flex gap-[var(--gap-tight)] overflow-x-auto pb-[var(--gap)]">
            {BOARD_ORDER.map((status) => (
              <Column key={status} status={status} rows={columns?.[status] ?? []}>
                {(columns?.[status] ?? []).map((row) => (
                  <Card
                    key={row.dedup_key}
                    row={row}
                    locale={i18n.language}
                    onOpen={() => setOpen(row)}
                    onMove={(next) => move.mutate({ key: row.dedup_key, next })}
                  />
                ))}
              </Column>
            ))}
          </div>
        </DndContext>
      )}

      {open ? (
        <Dialog title={open.posting.title} onClose={() => setOpen(null)}>
          <p className="text-[var(--text-small)] text-[var(--ink-soft)]">
            {open.posting.company}
            {open.posting.location ? ` · ${open.posting.location}` : ''}
          </p>
          <a
            href={open.posting.url}
            target="_blank"
            rel="noreferrer noopener"
            className="mono mt-[var(--gap-tight)] inline-block text-[var(--text-micro)] text-[var(--accent)] hover:underline"
          >
            {t('results.openAd')} ↗
          </a>

          {open.note ? (
            <p className="panel-sunk mt-[var(--gap)] px-[var(--gap)] py-[var(--gap-tight)] text-[var(--text-small)]">
              {open.note}
            </p>
          ) : null}

          <h3 className="eyebrow mt-[var(--gap-wide)]">{t('tracker.history')}</h3>
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
      ) : null}
    </>
  );
}
