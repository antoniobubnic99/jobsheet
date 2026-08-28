/**
 * Sheet designer, reached from a link rather than from the rail.
 *
 * The reason the project exists. Columns on the left, a live preview on the
 * right, and a write button that reads the workbook before it touches it.
 *
 * The layout is validated on the server as it is edited rather than at export
 * time. Learning that two columns share a key while still looking at the field
 * is a very different experience from learning it half an hour later when a
 * write fails.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, ApiError } from '@/lib/api';
import type { ExportReport, SheetLayout } from '@/lib/types';
import { keyFromLabel } from '@/lib/format';
import { screenNumber } from '@/lib/screens';
import {
  Loading,
  Note,
  Problem,
  ScreenHeader,
  Section,
  Toggle,
} from '@/components/primitives';
import ColumnList from '@/components/ColumnList';
import SheetPreview, { cssColour } from '@/components/SheetPreview';

export default function SheetDesigner() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();

  const current = useQuery({ queryKey: ['layout', 'current'], queryFn: api.currentLayout });
  const vocabulary = useQuery({ queryKey: ['layout', 'vocabulary'], queryFn: api.vocabulary });
  const presets = useQuery({ queryKey: ['layout', 'presets'], queryFn: api.presets });
  const savedNames = useQuery({
    queryKey: ['profiles', 'layout'],
    queryFn: () => api.profiles('layout'),
  });
  const sample = useQuery({
    queryKey: ['postings', 'sample'],
    queryFn: () => api.postings({ limit: 6 }),
  });
  const workbook = useQuery({ queryKey: ['workbook'], queryFn: api.workbookState });

  const [layout, setLayout] = useState<SheetLayout | null>(null);
  const [saveName, setSaveName] = useState('');
  const [written, setWritten] = useState<ExportReport | null>(null);

  // Open on whatever the workbook already uses, so a user who rearranged their
  // columns in Excel is not quietly offered the chance to undo it.
  useEffect(() => {
    if (current.data && !layout) setLayout(current.data.layout);
  }, [current.data, layout]);

  const check = useQuery({
    queryKey: ['layout', 'validate', layout],
    queryFn: () => api.validateLayout(layout as SheetLayout),
    enabled: Boolean(layout),
  });

  const write = useMutation({
    mutationFn: () => api.exportWorkbook({ layout: layout ?? undefined }),
    onSuccess: (report) => {
      setWritten(report);
      void queryClient.invalidateQueries({ queryKey: ['workbook'] });
      void queryClient.invalidateQueries({ queryKey: ['postings'] });
      void queryClient.invalidateQueries({ queryKey: ['board'] });
      void queryClient.invalidateQueries({ queryKey: ['layout', 'current'] });
    },
  });

  const theme = useMemo(
    () => vocabulary.data?.themes.find((entry) => entry.value === layout?.theme),
    [vocabulary.data, layout?.theme],
  );

  if (current.isLoading || !layout) return <Loading />;
  if (current.error) {
    return <Problem message={String(current.error)} onRetry={() => void current.refetch()} />;
  }

  const patch = (next: Partial<SheetLayout>) => {
    setLayout({ ...layout, ...next });
    setWritten(null);
  };

  const addColumn = () => {
    // A key nothing recognises is what makes it the user's own column; the
    // server marks it `user_owned` and then never writes to it.
    let key = 'my_note';
    let suffix = 1;
    while (layout.columns.some((column) => column.key === key)) {
      key = `my_note_${++suffix}`;
    }
    patch({
      columns: [
        ...layout.columns,
        { key, label: t('designer.customColumn'), kind: 'text', width: 22, wrap: false, user_owned: true },
      ],
    });
  };

  const problems = check.data && !check.data.valid ? check.data.problems : [];

  return (
    <>
      <ScreenHeader
        number={screenNumber('designer')}
        title={t('designer.title')}
        lede={t('designer.lede')}
        aside={
          <>
            <button
              type="button"
              className="btn btn-quiet"
              onClick={() => void api.downloadCsv({ layout })}
            >
              {t('designer.exportCsv')}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={write.isPending || problems.length > 0}
              onClick={() => write.mutate()}
            >
              {write.isPending ? t('designer.writing') : t('designer.exportWorkbook')}
            </button>
          </>
        }
      />

      {workbook.data?.locked ? (
        <div className="mt-[var(--gap-wide)]">
          <Note tone="warn">{t('designer.locked')}</Note>
        </div>
      ) : null}

      {write.error instanceof ApiError ? (
        <div className="mt-[var(--gap-wide)]">
          <Problem message={write.error.message} />
        </div>
      ) : null}

      {written ? (
        <div className="mt-[var(--gap-wide)] grid gap-[var(--gap-tight)]">
          <Note tone="ok">
            {t('designer.written', { rows: written.rows, path: written.path })}
            {written.backup ? ` ${t('designer.backupMade')}` : ''}
          </Note>
          {written.adopted_from_workbook.length ? (
            <Note tone="ok">
              {t('designer.adopted', { count: written.adopted_from_workbook.length })}
            </Note>
          ) : null}
        </div>
      ) : null}

      {problems.length ? (
        <div className="mt-[var(--gap-wide)]">
          <div
            role="alert"
            className="panel border-l-[3px] px-[var(--gap)] py-[var(--gap-tight)]"
            style={{ borderLeftColor: 'var(--bad)' }}
          >
            <p className="eyebrow" style={{ color: 'var(--bad)' }}>
              {t('designer.problems')}
            </p>
            <ul className="mt-[var(--gap-hair)] text-[var(--text-small)]">
              {problems.map((problem, index) => (
                <li key={index}>
                  <span className="mono text-[var(--text-micro)]">{problem.where}</span>{' '}
                  {problem.message}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {/* The asymmetry is the point: the preview is the hero and gets the wide
          half, the controls sit beside it and get exactly what they need. */}
      <div className="mt-[var(--gap-section)] grid gap-[var(--gap-section)] xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
        <div>
          <Section label={t('designer.columns')} hint={t('designer.columnsHelp')}>
            <ColumnList
              columns={layout.columns}
              vocabulary={vocabulary.data}
              onChange={(columns) =>
                patch({
                  // A key the user emptied would be refused by the server; a
                  // heading with no key at all is what they usually meant.
                  columns: columns.map((column) => ({
                    ...column,
                    key: column.key.trim() || keyFromLabel(column.label),
                  })),
                })
              }
            />
            <button type="button" className="btn btn-quiet mt-[var(--gap-tight)]" onClick={addColumn}>
              + {t('designer.addColumn')}
            </button>
            <p className="mt-[var(--gap-tight)] text-[var(--text-micro)] text-[var(--ink-faint)]">
              {t('designer.customKeyHelp')}
            </p>
          </Section>

          <Section label={t('designer.theme')}>
            <div className="flex flex-wrap gap-[var(--gap-tight)]">
              {(vocabulary.data?.themes ?? []).map((entry) => (
                <button
                  key={entry.value}
                  type="button"
                  className="panel flex items-center gap-[var(--gap-tight)] px-[var(--gap-tight)] py-[0.3rem] text-[var(--text-small)] transition-colors"
                  aria-pressed={layout.theme === entry.value}
                  style={{
                    borderColor: layout.theme === entry.value ? 'var(--accent)' : 'var(--rule)',
                    borderWidth: layout.theme === entry.value ? '2px' : '1px',
                  }}
                  onClick={() => patch({ theme: entry.value })}
                >
                  <span
                    aria-hidden
                    className="h-[1rem] w-[1.6rem] rounded-[2px] border"
                    style={{
                      background: cssColour(entry.header_fill, '#1F4E79'),
                      borderColor: cssColour(entry.border, '#BFC7D1'),
                    }}
                  />
                  {entry.value}
                </button>
              ))}
            </div>
          </Section>

          <Section label={t('designer.options')}>
            <div className="grid gap-[var(--gap-tight)]">
              <label className="block">
                <span className="eyebrow mb-[var(--gap-hair)] block">
                  {t('designer.sheetName')}
                </span>
                <input
                  className="field max-w-[16rem]"
                  value={layout.sheet_name}
                  onChange={(event) => patch({ sheet_name: event.target.value })}
                />
              </label>
              <Toggle
                label={t('designer.freeze')}
                checked={layout.freeze_header}
                onChange={(freeze_header) => patch({ freeze_header })}
              />
              <Toggle
                label={t('designer.autofilter')}
                checked={layout.autofilter}
                onChange={(autofilter) => patch({ autofilter })}
              />
              <Toggle
                label={t('designer.zebra')}
                checked={layout.zebra}
                onChange={(zebra) => patch({ zebra })}
              />
            </div>
          </Section>

          <Section label={t('designer.presets')}>
            <div className="grid gap-[var(--gap-tight)]">
              {(presets.data ?? []).map((preset) => (
                <button
                  key={preset.name}
                  type="button"
                  className="panel px-[var(--gap)] py-[var(--gap-tight)] text-left transition-colors hover:border-[var(--accent)]"
                  onClick={() => {
                    setLayout(preset.layout);
                    setWritten(null);
                  }}
                >
                  <span className="mono block text-[var(--text-small)] font-semibold">
                    {preset.name}
                  </span>
                  <span className="block text-[var(--text-micro)] leading-snug text-[var(--ink-soft)]">
                    {preset.description}
                  </span>
                </button>
              ))}
            </div>
          </Section>

          <Section label={t('designer.savedLayouts')}>
            <div className="flex flex-wrap items-center gap-[var(--gap-tight)]">
              <input
                className="field max-w-[14rem]"
                aria-label={t('designer.saveAs')}
                placeholder={t('search.namePlaceholder')}
                value={saveName}
                onChange={(event) => setSaveName(event.target.value)}
              />
              <button
                type="button"
                className="btn btn-quiet"
                disabled={!saveName.trim() || problems.length > 0}
                onClick={async () => {
                  await api.saveProfile('layout', saveName.trim(), layout);
                  setSaveName('');
                  void queryClient.invalidateQueries({ queryKey: ['profiles', 'layout'] });
                }}
              >
                {t('common.save')}
              </button>
            </div>

            <div className="mt-[var(--gap-tight)] flex flex-wrap gap-[var(--gap-hair)]">
              {(savedNames.data ?? []).map((name) => (
                <span
                  key={name}
                  className="panel flex items-center gap-[var(--gap-hair)] px-[var(--gap-tight)] py-[0.15rem]"
                >
                  <button
                    type="button"
                    className="text-[var(--text-small)] hover:text-[var(--accent)]"
                    onClick={async () => {
                      const loaded = await api.loadProfile<SheetLayout>('layout', name);
                      setLayout(loaded.payload);
                      setWritten(null);
                    }}
                  >
                    {name}
                  </button>
                  <button
                    type="button"
                    className="text-[var(--ink-faint)] hover:text-[var(--bad)]"
                    aria-label={`${t('common.delete')} ${name}`}
                    onClick={async () => {
                      await api.deleteProfile('layout', name);
                      void queryClient.invalidateQueries({ queryKey: ['profiles', 'layout'] });
                    }}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </Section>
        </div>

        <div className="xl:sticky xl:top-[var(--gap-wide)] xl:self-start">
          <Section label={t('designer.preview')}>
            <SheetPreview
              layout={layout}
              theme={theme}
              rows={sample.data?.rows ?? []}
              locale={i18n.language}
            />
          </Section>
        </div>
      </div>
    </>
  );
}
