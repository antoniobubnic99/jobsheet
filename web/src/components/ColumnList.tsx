/**
 * The column list, reorderable by drag.
 *
 * `dnd-kit` is used with the keyboard sensor enabled, so the order can be
 * changed without a mouse. A designer screen that only works by dragging is a
 * designer screen half the point of the app is closed to.
 */

import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useTranslation } from 'react-i18next';

import type { ColumnKind, ColumnSpec, LayoutVocabulary } from '@/lib/types';

function Row({
  column,
  vocabulary,
  onChange,
  onRemove,
  canRemove,
}: {
  column: ColumnSpec;
  vocabulary: LayoutVocabulary | undefined;
  onChange: (patch: Partial<ColumnSpec>) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: column.key,
  });

  return (
    <li
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.55 : 1,
        zIndex: isDragging ? 2 : undefined,
        position: 'relative',
      }}
      className="panel grid grid-cols-[auto_1fr] gap-[var(--gap-tight)] p-[var(--gap-tight)]"
    >
      <button
        type="button"
        className="btn btn-bare cursor-grab self-start px-[0.3rem] text-[var(--ink-faint)] active:cursor-grabbing"
        aria-label={`Reorder ${column.label}`}
        {...attributes}
        {...listeners}
      >
        ⠿
      </button>

      <div className="grid gap-[var(--gap-tight)]">
        <div className="flex flex-wrap items-center gap-[var(--gap-tight)]">
          <input
            className="field flex-1"
            aria-label={`${t('designer.label')} — ${column.key}`}
            value={column.label}
            onChange={(event) => onChange({ label: event.target.value })}
          />
          {column.user_owned ? (
            <span
              className="rounded-[var(--radius-round)] px-[0.45rem] py-[0.05rem] text-[var(--text-micro)] font-semibold uppercase tracking-[0.08em]"
              style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}
              title={t('designer.yoursHelp')}
            >
              {t('designer.yours')}
            </span>
          ) : null}
          <button
            type="button"
            className="btn btn-bare"
            style={{ color: 'var(--bad)' }}
            disabled={!canRemove}
            onClick={onRemove}
            aria-label={`${t('designer.remove')} ${column.label}`}
          >
            ×
          </button>
        </div>

        <div className="grid grid-cols-[1fr_auto_auto] items-end gap-[var(--gap-tight)]">
          <label className="min-w-0">
            <span className="eyebrow mb-[var(--gap-hair)] block">{t('designer.key')}</span>
            <input
              className="field mono text-[var(--text-micro)]"
              value={column.key}
              onChange={(event) => onChange({ key: event.target.value })}
              list="jobsheet-source-keys"
            />
          </label>

          <label>
            <span className="eyebrow mb-[var(--gap-hair)] block">{t('designer.kind')}</span>
            <select
              className="field text-[var(--text-micro)]"
              value={column.kind}
              onChange={(event) => onChange({ kind: event.target.value as ColumnKind })}
            >
              {(vocabulary?.kinds ?? []).map((kind) => (
                <option key={kind.value} value={kind.value}>
                  {kind.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className="eyebrow mb-[var(--gap-hair)] block">{t('designer.width')}</span>
            <input
              type="number"
              min={4}
              max={120}
              className="field tabular w-[4.5rem] text-[var(--text-micro)]"
              value={column.width}
              onChange={(event) => onChange({ width: Number(event.target.value) || 18 })}
            />
          </label>
        </div>
      </div>
    </li>
  );
}

export default function ColumnList({
  columns,
  vocabulary,
  onChange,
}: {
  columns: ColumnSpec[];
  vocabulary: LayoutVocabulary | undefined;
  onChange: (next: ColumnSpec[]) => void;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = columns.findIndex((column) => column.key === active.id);
    const to = columns.findIndex((column) => column.key === over.id);
    if (from < 0 || to < 0) return;
    onChange(arrayMove(columns, from, to));
  };

  return (
    <>
      {/* The datalist is what turns a free-text key field into a helpful one:
          the recognised keys are offered, anything else is a custom column. */}
      <datalist id="jobsheet-source-keys">
        {(vocabulary?.source_keys ?? []).map((key) => (
          <option key={key} value={key} />
        ))}
      </datalist>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        modifiers={[restrictToVerticalAxis]}
        onDragEnd={onDragEnd}
      >
        <SortableContext
          items={columns.map((column) => column.key)}
          strategy={verticalListSortingStrategy}
        >
          <ul className="grid gap-[var(--gap-tight)]">
            {columns.map((column, index) => (
              <Row
                key={column.key}
                column={column}
                vocabulary={vocabulary}
                canRemove={columns.length > 1}
                onChange={(patch) =>
                  onChange(
                    columns.map((item, position) =>
                      position === index ? { ...item, ...patch } : item,
                    ),
                  )
                }
                onRemove={() => onChange(columns.filter((_, position) => position !== index))}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
    </>
  );
}
