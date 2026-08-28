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
 * * **The arrows** exist because the board is a horizontally scrolling row, and
 *   dragging a card between columns on a phone means dragging it past the edge
 *   of the screen and hoping the board scrolls under it. It does not.
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
import { formatDate, formatWhen } from '@/lib/format';
import { screenNumber } from '@/lib/screens';
import {
  Dialog,
  Empty,
  Loading,
  Problem,
  ScreenHeader,
  StatusPill,
} from '@/components/primitives';
import LetterDialog from '@/components/LetterDialog';

const KNOWN_STATUSES = new Set<string>(BOARD_ORDER);

/** Keep a pointer gesture from reaching the card underneath it. */
const KEEP_TO_ITSELF = {
  onPointerDown: (event: React.PointerEvent) => event.stopPropagation(),
  onClick: (event: React.MouseEvent) => event.stopPropagation(),
};

function StatusSelect({
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
      className="flex min-w-[12.5rem] flex-1 flex-col rounded-[var(--radius)] transition-colors"
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
  const history = useQuery({
    queryKey: ['history', openKey],
    queryFn: () => api.history(openKey!),
    enabled: Boolean(openKey),
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
          {/* Plain `overflow-x`, not `.scroll-x`: paint containment would clip a
              card the moment it was dragged past the edge of the board. */}
          <div className="mt-[var(--gap-wide)] flex gap-[var(--gap-tight)] overflow-x-auto pb-[var(--gap)]">
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
        <Dialog title={open.posting.title} onClose={() => setOpenKey(null)}>
          <p className="text-[var(--text-small)] text-[var(--ink-soft)]">
            {open.posting.company}
            {open.posting.location ? ` · ${open.posting.location}` : ''}
          </p>

          {/* Everything you would otherwise have closed the dialog to do. It
              held the ad link and a note and nothing else, which left the one
              screen that is about deciding unable to act on a decision. */}
          <div className="mt-[var(--gap)] flex flex-wrap items-center gap-[var(--gap-tight)]">
            <StatusPill status={open.status} />
            <StatusSelect
              row={open}
              order={order}
              onMove={(next) => move.mutate({ key: open.dedup_key, next })}
              className="text-[var(--text-small)]"
            />
          </div>

          <div className="mt-[var(--gap)] flex flex-wrap items-center gap-[var(--gap-tight)]">
            <a
              href={open.posting.url}
              target="_blank"
              rel="noreferrer noopener"
              className="btn btn-quiet"
            >
              {t('results.openAd')} ↗
            </a>
            <button
              type="button"
              className="btn btn-quiet"
              onClick={() => {
                setLetterFor(open);
                setOpenKey(null);
              }}
            >
              {t('results.letter')}
            </button>
            {open.status === 'skipped' ? null : (
              <button
                type="button"
                className="btn btn-bare text-[var(--ink-faint)] hover:text-[var(--bad)]"
                onClick={() => move.mutate({ key: open.dedup_key, next: 'skipped' })}
              >
                {t('tracker.discard')}
              </button>
            )}
          </div>

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

      {letterFor ? <LetterDialog row={letterFor} onClose={() => setLetterFor(null)} /> : null}
    </>
  );
}
