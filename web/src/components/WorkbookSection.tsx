/**
 * Where the workbook lives, and how to move it.
 *
 * The wizard asks this once, on the first day, and until now that was the last
 * word: the settings screen showed the path and there was no route that could
 * change it. People buy laptops, reorganise their Documents folder, and decide
 * a month in that the spreadsheet belongs in Dropbox after all -- and the only
 * remedy was a new account.
 *
 * The checkbox is the part that matters. Changing the path without moving the
 * file leaves a year of hand-typed ticks in a workbook JobSheet has stopped
 * looking at, and the person finds out the next time they open the spreadsheet
 * they have been keeping and see nothing new in it. So the file comes along by
 * default, and the server refuses to move one that is open in Excel or to write
 * over one already at the far end.
 */

import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api, ApiError } from '@/lib/api';
import { ACCOUNT_KEY } from '@/lib/account';
import type { AppSettings } from '@/lib/types';
import { Note, Section, Toggle } from '@/components/primitives';
import FolderPicker from '@/components/FolderPicker';

/** Split a path into the folder it is in and the file it is, either separator. */
function split(path: string): { folder: string; name: string } {
  const cut = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'));
  return cut < 0
    ? { folder: '', name: path }
    : { folder: path.slice(0, cut), name: path.slice(cut + 1) };
}

function join(folder: string, name: string): string {
  const separator = folder.includes('\\') ? '\\' : '/';
  return folder.endsWith(separator) ? `${folder}${name}` : `${folder}${separator}${name}`;
}

export default function WorkbookSection({ settings }: { settings: AppSettings }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const current = split(settings.workbook);

  const [editing, setEditing] = useState(false);
  const [folder, setFolder] = useState(current.folder);
  const [name, setName] = useState(current.name);
  const [move, setMove] = useState(true);
  const [done, setDone] = useState('');

  // Opening the editor starts from wherever the workbook is now, even if the
  // last attempt was abandoned half-typed.
  useEffect(() => {
    if (!editing) return;
    setFolder(current.folder);
    setName(current.name);
    setDone('');
    // Only when the editor opens: re-syncing on every render would fight typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  const change = useMutation({
    mutationFn: () => api.setWorkbook(join(folder, name.trim()), move),
    onSuccess: (result) => {
      setEditing(false);
      setDone(result.moved ? t('settings.workbookMoved') : t('settings.workbookPointed'));
      // The path shows on this screen, in the account, and behind every export
      // and layout answer, all of which were computed from the old one.
      void queryClient.invalidateQueries({ queryKey: ['settings'] });
      void queryClient.invalidateQueries({ queryKey: ACCOUNT_KEY });
      void queryClient.invalidateQueries({ queryKey: ['workbook'] });
      void queryClient.invalidateQueries({ queryKey: ['layout'] });
    },
  });

  const failure = change.error;
  const message =
    failure instanceof ApiError
      ? t(`auth.errors.${failure.code}`, { defaultValue: failure.message })
      : failure
        ? t('error.generic')
        : '';

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!folder.trim() || !name.trim()) return;
    change.mutate();
  };

  return (
    <Section
      label={t('settings.workbook')}
      hint={t('settings.workbookHint')}
      aside={
        <button type="button" className="btn btn-quiet" onClick={() => setEditing(!editing)}>
          {editing ? t('common.cancel') : t('settings.changeWorkbook')}
        </button>
      }
    >
      <div className="panel p-[var(--gap-wide)]">
        <p className="mono break-all text-[var(--text-small)]">{settings.workbook}</p>
        <p className="mt-[var(--gap-hair)] text-[var(--text-micro)] text-[var(--ink-faint)]">
          {settings.workbook_locked
            ? t('settings.workbookLocked')
            : settings.workbook_exists
              ? t('settings.workbookReady')
              : t('settings.workbookMissing')}
        </p>

        {done ? (
          <p
            className="mt-[var(--gap)] border-l-[3px] pl-[var(--gap-tight)] text-[var(--text-small)]"
            style={{ borderLeftColor: 'var(--ok)' }}
          >
            {done}
          </p>
        ) : null}

        {editing ? (
          <form onSubmit={onSubmit} className="rule-t mt-[var(--gap)] pt-[var(--gap)]">
            <p className="eyebrow mb-[var(--gap-tight)]">{t('settings.folder')}</p>
            <FolderPicker value={folder} onChange={setFolder} />

            <label className="mt-[var(--gap)] block">
              <span className="eyebrow mb-[var(--gap-hair)] block">
                {t('settings.workbookName')}
              </span>
              <input
                className="field mono"
                value={name}
                spellCheck={false}
                onChange={(event) => setName(event.target.value)}
              />
            </label>

            <p className="mono mt-[var(--gap-tight)] break-all text-[var(--text-micro)] text-[var(--ink-faint)]">
              {join(folder, name.trim())}
            </p>

            <div className="mt-[var(--gap)]">
              <Toggle checked={move} onChange={setMove} label={t('settings.moveWorkbook')} />
              {move ? null : (
                <div className="mt-[var(--gap-tight)]">
                  <Note tone="warn">{t('settings.moveWorkbookWarning')}</Note>
                </div>
              )}
            </div>

            {message ? (
              <p
                role="alert"
                className="mt-[var(--gap-tight)] border-l-[3px] pl-[var(--gap-tight)] text-[var(--text-small)]"
                style={{ borderLeftColor: 'var(--bad)' }}
              >
                {message}
              </p>
            ) : null}

            <button
              type="submit"
              className="btn btn-quiet mt-[var(--gap)]"
              disabled={change.isPending || !folder.trim() || !name.trim()}
            >
              {change.isPending ? t('auth.working') : t('common.save')}
            </button>
          </form>
        ) : null}
      </div>
    </Section>
  );
}
