/**
 * The keyword groups, in the order they are tried.
 *
 * The order is meaningful and the interface says so: the first group that
 * matches names the job's category, which is how a user expresses "I would
 * rather be told this is a GIS job than a Data job". Moving a group up or down
 * therefore changes the answer, not just the display.
 */

import { useTranslation } from 'react-i18next';

import type { KeywordGroup } from '@/lib/types';
import { ChipInput, Empty } from '@/components/primitives';

export default function KeywordGroups({
  groups,
  onChange,
}: {
  groups: KeywordGroup[];
  onChange: (next: KeywordGroup[]) => void;
}) {
  const { t } = useTranslation();

  const update = (index: number, patch: Partial<KeywordGroup>) =>
    onChange(groups.map((group, position) => (position === index ? { ...group, ...patch } : group)));

  const move = (index: number, by: number) => {
    const target = index + by;
    if (target < 0 || target >= groups.length) return;
    const next = [...groups];
    const [moved] = next.splice(index, 1);
    if (moved) next.splice(target, 0, moved);
    onChange(next);
  };

  return (
    <div className="grid gap-[var(--gap-tight)]">
      {groups.length === 0 ? <Empty>{t('common.nothing')}</Empty> : null}

      {groups.map((group, index) => (
        <div key={index} className="panel grid gap-[var(--gap)] p-[var(--gap)] md:grid-cols-[minmax(0,14rem)_1fr_auto]">
          <div>
            <label className="eyebrow mb-[var(--gap-hair)] block" htmlFor={`group-${index}`}>
              <span className="mono mr-[0.4rem] text-[var(--accent)]">{index + 1}</span>
              {t('search.groupName')}
            </label>
            <input
              id={`group-${index}`}
              className="field"
              value={group.name}
              onChange={(event) => update(index, { name: event.target.value })}
            />
          </div>

          <div>
            <span className="eyebrow mb-[var(--gap-hair)] block">{t('search.terms')}</span>
            <ChipInput
              ariaLabel={`${t('search.terms')} ${group.name || index + 1}`}
              values={group.terms}
              placeholder={t('search.termPlaceholder')}
              onChange={(terms) => update(index, { terms })}
            />
          </div>

          <div className="flex items-end gap-[var(--gap-hair)]">
            <button
              type="button"
              className="btn btn-bare"
              disabled={index === 0}
              onClick={() => move(index, -1)}
              aria-label="Move up"
            >
              ↑
            </button>
            <button
              type="button"
              className="btn btn-bare"
              disabled={index === groups.length - 1}
              onClick={() => move(index, 1)}
              aria-label="Move down"
            >
              ↓
            </button>
            <button
              type="button"
              className="btn btn-bare"
              style={{ color: 'var(--bad)' }}
              onClick={() => onChange(groups.filter((_, position) => position !== index))}
              aria-label={t('search.removeGroup')}
            >
              ×
            </button>
          </div>
        </div>
      ))}

      <div>
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => onChange([...groups, { name: '', terms: [] }])}
        >
          + {t('search.addGroup')}
        </button>
      </div>
    </div>
  );
}
