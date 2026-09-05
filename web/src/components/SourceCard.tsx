/**
 * One source, and the form it asked for.
 *
 * The form is built from the manifest, field by field. Nothing here knows what
 * Greenhouse or HZZ needs -- that is the point of the plugin design, and this
 * component is where it pays off: a third-party source published tomorrow gets
 * a working form today.
 */

import { useTranslation } from 'react-i18next';

import type { ParamSpec, SourceManifest } from '@/lib/types';
import { formatWhen } from '@/lib/format';
import { normalizeAtsSlug } from '@/lib/sourceDefaults';

function ParamField({
  spec,
  value,
  onChange,
  fieldId,
  sourceId,
}: {
  spec: ParamSpec;
  value: unknown;
  onChange: (next: unknown) => void;
  /** Namespaced by source id: two sources sharing a param name (both have
      a `days`, say) would otherwise render two fields with the same DOM id
      once both are ticked -- which breaks the label's association with
      whichever one comes second, silently, since duplicate ids are valid
      HTML and nothing here would ever throw about it. */
  fieldId: string;
  /** Which source this field belongs to, so a bare board/account/company
      slug can forgive a pasted full address on the four ATS sources. */
  sourceId: string;
}) {
  const id = fieldId;

  if (spec.kind === 'boolean') {
    return (
      <label className="flex items-center gap-[var(--gap-tight)] text-[var(--text-small)]">
        <input
          id={id}
          type="checkbox"
          className="accent-[var(--accent)]"
          checked={Boolean(value)}
          onChange={(event) => onChange(event.target.checked)}
        />
        {spec.label}
      </label>
    );
  }

  return (
    <div>
      <label htmlFor={id} className="eyebrow mb-[var(--gap-hair)] block">
        {spec.label}
        {spec.required ? <span style={{ color: 'var(--bad)' }}> *</span> : null}
      </label>

      {spec.kind === 'select' || spec.kind === 'multiselect' ? (
        <select
          id={id}
          className="field"
          multiple={spec.kind === 'multiselect'}
          value={
            spec.kind === 'multiselect'
              ? ((value as string[] | undefined) ?? [])
              : ((value as string | undefined) ?? String(spec.default ?? ''))
          }
          onChange={(event) =>
            onChange(
              spec.kind === 'multiselect'
                ? [...event.target.selectedOptions].map((option) => option.value)
                : event.target.value,
            )
          }
        >
          {spec.kind === 'select' && !spec.required ? <option value="" /> : null}
          {spec.choices.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          className="field"
          type={spec.kind === 'number' ? 'number' : spec.kind === 'url' ? 'url' : 'text'}
          placeholder={spec.placeholder}
          value={(value as string | number | undefined) ?? ''}
          onChange={(event) =>
            onChange(spec.kind === 'number' ? Number(event.target.value) : event.target.value)
          }
          onBlur={
            spec.kind === 'text'
              ? (event) => onChange(normalizeAtsSlug(sourceId, spec.name, event.target.value))
              : undefined
          }
        />
      )}

      {spec.help ? (
        <p className="mt-[var(--gap-hair)] text-[var(--text-micro)] leading-snug text-[var(--ink-faint)]">
          {spec.help}
        </p>
      ) : null}
    </div>
  );
}

export default function SourceCard({
  source,
  chosen,
  params,
  onToggle,
  onParams,
  locale,
}: {
  source: SourceManifest;
  chosen: boolean;
  params: Record<string, unknown>;
  onToggle: (id: string, defaults: Record<string, unknown>) => void;
  onParams: (id: string, params: Record<string, unknown>) => void;
  locale: string;
}) {
  const { t } = useTranslation();
  const health = source.health;

  const defaults = Object.fromEntries(
    source.params.filter((spec) => spec.default != null).map((spec) => [spec.name, spec.default]),
  );

  return (
    <div
      className="panel flex flex-col transition-colors"
      style={{
        borderColor: chosen ? 'var(--accent)' : 'var(--rule)',
        background: chosen ? 'var(--surface-raised)' : 'var(--surface)',
      }}
    >
      <label className="flex cursor-pointer items-start gap-[var(--gap-tight)] p-[var(--gap)]">
        <input
          type="checkbox"
          className="mt-[0.25rem] accent-[var(--accent)]"
          checked={chosen}
          onChange={() => onToggle(source.id, defaults)}
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-[var(--gap-tight)]">
            <span className="font-semibold">{source.name}</span>
            <span className="mono text-[var(--text-micro)] text-[var(--ink-faint)]">
              {source.id}
            </span>
          </span>
          {source.description ? (
            <span className="mt-[var(--gap-hair)] block text-[var(--text-small)] leading-snug text-[var(--ink-soft)]">
              {source.description}
            </span>
          ) : null}

          {/* Health is shown on the card rather than buried in settings: which
              source went quiet is the first question when results thin out. */}
          <span
            className="mt-[var(--gap-tight)] block text-[var(--text-micro)]"
            style={{
              color: !health
                ? 'var(--ink-faint)'
                : health.last_error && !health.last_ok
                  ? 'var(--bad)'
                  : 'var(--ok)',
            }}
          >
            {!health
              ? t('search.healthUnknown')
              : health.last_error && !health.last_ok
                ? t('search.healthBad', { when: formatWhen(health.last_error, locale) })
                : t('search.healthOk', { when: formatWhen(health.last_ok, locale) })}
            {/* The timestamp alone says a source is unwell, not why -- the
                board slug is wrong, the site is down, the token expired. The
                reason lives here rather than only in Settings, because this
                is where somebody is actually looking when it matters. */}
            {health?.message ? (
              <span className="mt-[var(--gap-hair)] block text-[var(--ink-faint)]">
                {health.message}
              </span>
            ) : null}
          </span>
        </span>
      </label>

      {chosen && source.params.length ? (
        <div className="rule-t grid gap-[var(--gap-tight)] p-[var(--gap)]">
          {source.params.map((spec) => (
            <ParamField
              key={spec.name}
              spec={spec}
              value={params[spec.name]}
              onChange={(next) => onParams(source.id, { ...params, [spec.name]: next })}
              fieldId={`param-${source.id}-${spec.name}`}
              sourceId={source.id}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
