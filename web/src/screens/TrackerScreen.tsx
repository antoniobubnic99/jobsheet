/**
 * The tracker.
 *
 * A board, with one design decision worth naming: `Discarded` is the first
 * column and `Rejected` the last. "I decided against it" and "they decided
 * against me" are different stories, and a board that files them together loses
 * something the person looking at it cares about. Discarded leads because that
 * is where most cards end up and where nobody wants to look -- first column,
 * out of the way of the four that tell the story.
 *
 * The column order comes from the server, not from a constant here. It used to
 * come from both, which is two places for one fact and a guarantee that they
 * would drift.
 *
 * ## Three ways to move a card, on purpose
 *
 * A card can be dragged from anywhere on it, moved with the arrows above its
 * column, or set with the select on the card itself. That is not indulgence:
 *
 * * **Dragging** is what people reach for, and restricting it to a small handle
 *   made the obvious gesture fail on the first try.
 * * **The arrows** exist because the board is a wrapping grid, not a scrolling
 *   row: on a narrow screen the columns sit close together and a drag can
 *   easily land one column off from where it was meant to.
 * * **The select** is the only one of the three a keyboard can operate, so it
 *   stays whatever else changes.
 *
 * Dragging and clicking share the same surface, which works because the pointer
 * sensor only starts a drag after 5px of movement -- and dnd-kit swallows the
 * click that follows a real drag, so a card cannot be dropped and opened at
 * once. Anything interactive *inside* a card stops the gesture itself, or a
 * drag would begin every time somebody reached for the status select.
 */

import { useMemo, useState } from 'react';
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
import { formatDate } from '@/lib/format';
import { screenNumber } from '@/lib/screens';
import { Empty, Loading, Problem, ScreenHeader, StatusPill } from '@/components/primitives';
import JobDetailDialog, { StatusSelect } from '@/components/JobDetailDialog';
import LetterDialog from '@/components/LetterDialog';

const KNOWN_STATUSES = new Set<string>(BOARD_ORDER);

function Card({
  row,
  order,
  onOpen,
  onMove,
  locale,
}: {
  row: JobRow;
  order: ApplicationStatus[];
  onOpen: () => void;
  onMove: (next: ApplicationStatus) => void;
  locale: string;
}) {
  const { t } = useTranslation();
  const { listeners, setNodeRef, transform, isDragging } = useDraggable({
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
      className="panel grid cursor-grab gap-[var(--gap-hair)] p-[var(--gap-tight)] active:cursor-grabbing"
      onClick={onOpen}
      {...listeners}
    >
      {/* A button, not merely a clickable card: the card handles the pointer,
          this handles the keyboard, and both open the same dialog. */}
      <button
        type="button"
        className="min-w-0 text-left text-[var(--text-small)] font-semibold leading-snug hover:text-[var(--accent)]"
        onClick={onOpen}
      >
        {row.posting.title}
      </button>

      <p className="text-[var(--text-micro)] text-[var(--ink-soft)]">
        {row.posting.company}
        {row.posting.location ? ` · ${row.posting.location}` : ''}
      </p>

      {/* Wrapping, not clipping: a column is 12.5rem wide and a date beside a
          select does not always fit in one. */}
      <div className="flex flex-wrap items-center justify-between gap-[var(--gap-hair)]">
        <span className="mono text-[var(--text-micro)] text-[var(--ink-faint)]">
          {formatDate(row.found_at, locale)}
        </span>
        <StatusSelect
          row={row}
          order={order}
          onMove={onMove}
          className="py-[0.05rem] text-[var(--text-micro)]"
        />
      </div>

      <span className="sr-only">{t('tracker.openHint')}</span>
    </article>
  );
}

function Column({
  status,
  rows,
  leftTo,
  rightTo,
  onShift,
  children,
}: {
  status: ApplicationStatus;
  rows: JobRow[];
  /** The neighbouring columns, or `null` at either end of the board. */
  leftTo: ApplicationStatus | null;
  rightTo: ApplicationStatus | null;
  onShift: (to: ApplicationStatus) => void;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({ id: status });
  const top = rows[0];

  const arrow = (to: ApplicationStatus | null, glyph: string) => (
    <button
      type="button"
      className="btn btn-bare px-[0.35rem] text-[var(--ink-faint)] enabled:hover:text-[var(--accent)] disabled:opacity-30"
      disabled={!to || !top}
      aria-label={
        to && top
          ? t('tracker.moveTopTo', { title: top.posting.title, column: t(`status.${to}`) })
          : t('tracker.cannotMove')
      }
      onClick={() => to && onShift(to)}
    >
      {glyph}
    </button>
  );

  return (
    <section
      ref={setNodeRef}
      className="flex flex-col rounded-[var(--radius)] transition-colors"
      style={{
        background: isOver ? `var(--status-${status}-soft)` : 'var(--ground-sunk)',
        outline: isOver ? `1px dashed var(--status-${status})` : '1px solid var(--rule)',
      }}
    >
      <header
        className="rule-b flex items-center justify-between gap-[var(--gap-hair)] px-[var(--gap-hair)] py-[var(--gap-hair)]"
        style={{ borderBottomColor: `var(--status-${status})` }}
      >
        {arrow(leftTo, '‹')}
        <StatusPill status={status} />
        <span className="mono text-[var(--text-micro)] text-[var(--ink-faint)]">
          {rows.length}
        </span>
        {arrow(rightTo, '›')}
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
  /* The key rather than the row: a held row goes stale the moment the card
     moves, and a dialog still showing the old status after you changed it from
     inside that dialog would be its own small bug. */
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [letterFor, setLetterFor] = useState<JobRow | null>(null);

  const board = useQuery({ queryKey: ['board'], queryFn: api.board });

  const move = useMutation({
    mutationFn: ({ key, next }: { key: string; next: ApplicationStatus }) => api.move(key, next),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['board'] });
      void queryClient.invalidateQueries({ queryKey: ['postings'] });
      void queryClient.invalidateQueries({ queryKey: ['history'] });
    },
  });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const columns = board.data?.columns;
  const served = board.data?.order;

  /** The board's own column order, with the constant as a fallback. */
  const order = useMemo<ApplicationStatus[]>(() => {
    const known = (served ?? []).filter((status): status is ApplicationStatus =>
      KNOWN_STATUSES.has(status),
    );
    return known.length ? known : BOARD_ORDER;
  }, [served]);

  const open = useMemo<JobRow | null>(() => {
    if (!openKey || !columns) return null;
    for (const rows of Object.values(columns)) {
      const found = rows.find((row) => row.dedup_key === openKey);
      if (found) return found;
    }
    return null;
  }, [openKey, columns]);

  const onDragEnd = (event: DragEndEvent) => {
    const next = event.over?.id as ApplicationStatus | undefined;
    if (!next) return;
    move.mutate({ key: String(event.active.id), next });
  };

  if (board.isLoading) return <Loading />;
  if (board.error) {
    return <Problem message={String(board.error)} onRetry={() => void board.refetch()} />;
  }

  const anything = Object.values(columns ?? {}).some((rows) => rows.length > 0);

  return (
    <>
      <ScreenHeader
        number={screenNumber('tracker')}
        title={t('tracker.title')}
        lede={t('tracker.lede')}
      />

      {!anything ? (
        <div className="mt-[var(--gap-wide)]">
          <Empty>{t('tracker.boardEmpty')}</Empty>
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragEnd={onDragEnd}>
          {/* A wrapping grid, not a scrolling row: `1fr` tracks cannot sum to
              more than the container, so all six columns fit at once on a
              real desktop width with no scrollbar to fight. Narrower than
              that, columns wrap into more rows instead of running off the
              edge of the screen -- which is also why the arrows above a
              column still earn their keep on a phone: columns sit close
              together there, and a drag can land in the wrong one. */}
          <div className="mt-[var(--gap-wide)] grid grid-cols-2 gap-[var(--gap-tight)] pb-[var(--gap)] sm:grid-cols-3 xl:grid-cols-6">
            {order.map((status, index) => {
              const rows = columns?.[status] ?? [];
              return (
                <Column
                  key={status}
                  status={status}
                  rows={rows}
                  leftTo={order[index - 1] ?? null}
                  rightTo={order[index + 1] ?? null}
                  onShift={(to) => {
                    const top = rows[0];
                    if (top) move.mutate({ key: top.dedup_key, next: to });
                  }}
                >
                  {rows.map((row) => (
                    <Card
                      key={row.dedup_key}
                      row={row}
                      order={order}
                      locale={i18n.language}
                      onOpen={() => setOpenKey(row.dedup_key)}
                      onMove={(next) => move.mutate({ key: row.dedup_key, next })}
                    />
                  ))}
                </Column>
              );
            })}
          </div>
        </DndContext>
      )}

      {open ? (
        <JobDetailDialog
          row={open}
          order={order}
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

      {letterFor ? <LetterDialog row={letterFor} onClose={() => setLetterFor(null)} /> : null}
    </>
  );
}
