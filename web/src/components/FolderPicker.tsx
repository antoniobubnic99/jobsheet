/**
 * Choosing a folder by looking at folders.
 *
 * A browser cannot open the operating system's file dialog for a page -- for
 * good reasons, none of which help somebody who has to type
 * `C:\Users\ana\OneDrive\Dokumenti` correctly from memory. So the server, which
 * is on this machine and answers only this machine, lists the folders inside
 * one folder and this walks them.
 *
 * It lists folder names and nothing else: no files, no sizes, no contents. That
 * is a narrower view of the disk than the file dialog every other program on
 * the laptop opens, and it goes no further than the page JobSheet served.
 *
 * The current folder is shown as text and is editable, because for the person
 * who *does* know the path, typing it is faster than eight clicks.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';

export default function FolderPicker({
  value,
  onChange,
}: {
  /** The folder currently chosen. Empty asks the server where to start. */
  value: string;
  onChange: (folder: string) => void;
}) {
  const { t } = useTranslation();
  const [typed, setTyped] = useState(value);

  const listing = useQuery({
    queryKey: ['folders', value],
    queryFn: () => api.folders(value),
  });

  // The server decides where an empty or stale path lands, so the field
  // follows what came back rather than what was asked for.
  const here = listing.data?.path ?? value;
  const showing = typed === value ? here : typed;

  const go = (folder: string) => {
    setTyped(folder);
    onChange(folder);
  };

  return (
    <div className="panel-sunk grid gap-[var(--gap-tight)] p-[var(--gap-tight)]">
      <div className="flex flex-wrap items-center gap-[var(--gap-hair)]">
        <button
          type="button"
          className="btn btn-quiet"
          disabled={!listing.data?.parent}
          onClick={() => listing.data?.parent && go(listing.data.parent)}
        >
          ↑ {t('settings.folderUp')}
        </button>
        <button
          type="button"
          className="btn btn-bare text-[var(--text-micro)]"
          onClick={() => listing.data?.home && go(listing.data.home)}
        >
          {t('settings.folderHome')}
        </button>
        {(listing.data?.roots ?? []).map((root) => (
          <button
            key={root.path}
            type="button"
            className="btn btn-bare mono text-[var(--text-micro)]"
            onClick={() => go(root.path)}
          >
            {root.name}
          </button>
        ))}
      </div>

      <label className="block">
        <span className="sr-only">{t('settings.folder')}</span>
        <input
          className="field mono text-[var(--text-micro)]"
          value={showing}
          spellCheck={false}
          onChange={(event) => setTyped(event.target.value)}
          onBlur={() => typed.trim() && go(typed.trim())}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              if (typed.trim()) go(typed.trim());
            }
          }}
        />
      </label>

      <ul className="max-h-[11rem] overflow-y-auto">
        {(listing.data?.folders ?? []).map((folder) => (
          <li key={folder.path}>
            <button
              type="button"
              className="block w-full truncate px-[var(--gap-tight)] py-[var(--gap-hair)] text-left text-[var(--text-small)] transition-colors hover:bg-[var(--surface)]"
              onClick={() => go(folder.path)}
            >
              {folder.name}
            </button>
          </li>
        ))}
        {listing.data && listing.data.folders.length === 0 ? (
          <li className="px-[var(--gap-tight)] py-[var(--gap-hair)] text-[var(--text-micro)] text-[var(--ink-faint)]">
            {listing.data.message || t('settings.folderEmpty')}
          </li>
        ) : null}
      </ul>

      {listing.data && !listing.data.writable ? (
        <p className="text-[var(--text-micro)]" style={{ color: 'var(--bad)' }}>
          {t('settings.folderReadOnly')}
        </p>
      ) : null}
    </div>
  );
}
