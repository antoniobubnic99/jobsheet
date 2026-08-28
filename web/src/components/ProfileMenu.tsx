/**
 * Who is signed in, and the three things you do about it.
 *
 * It used to be a name and a "Sign out" pinned to the bottom of the rail,
 * behind `hidden md:block` -- which meant that on a phone the interface never
 * told you whose search you were looking at and gave you no way out of it. On
 * an app whose whole premise is that one laptop holds several people's job
 * searches, that is not a cosmetic gap.
 *
 * Signing out asks first. Not because signing out is dangerous -- nothing is
 * lost -- but because the button is now reachable at every width, next to the
 * two links people use daily, and the cost of a mis-tap is retyping a password
 * you may well have forgotten. The question is asked in place rather than in a
 * `confirm()` box, so it cannot be dismissed by the click that opened it.
 */

import { useEffect, useRef, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useAccount } from '@/lib/account';
import { MY_SEARCH } from '@/lib/screens';

const ITEM =
  'block w-full px-[var(--gap)] py-[var(--gap-tight)] text-left text-[var(--text-small)] transition-colors hover:bg-[var(--surface)]';

export default function ProfileMenu({ className = '' }: { className?: string }) {
  const { t } = useTranslation();
  const { account, signOut } = useAccount();
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  const close = () => {
    setOpen(false);
    setAsking(false);
  };

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    // `pointerdown` rather than `click`: a menu that waits for the full click
    // stays open under the thing you just tapped, which reads as a stuck menu.
    const onOutside = (event: PointerEvent) => {
      if (!box.current?.contains(event.target as Node)) close();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onOutside);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onOutside);
    };
  }, [open]);

  if (!account) return null;

  const initial = account.username.slice(0, 1).toUpperCase();

  return (
    <div ref={box} className={`relative ${className}`}>
      <button
        type="button"
        className="flex w-full items-center gap-[var(--gap-tight)] px-[var(--gap-wide)] py-[var(--gap-tight)] text-left transition-colors hover:bg-[var(--surface)]"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => (open ? close() : setOpen(true))}
      >
        <span
          aria-hidden
          className="grid h-[1.6rem] w-[1.6rem] shrink-0 place-items-center rounded-full bg-[var(--accent-soft)] text-[var(--text-micro)] font-bold text-[var(--accent)]"
        >
          {initial}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[var(--text-small)] font-semibold">
            {account.username}
          </span>
          <span className="block text-[var(--text-micro)] leading-snug text-[var(--ink-faint)]">
            {t('auth.profile')}
          </span>
        </span>
        <span aria-hidden className="text-[var(--text-micro)] text-[var(--ink-faint)]">
          {open ? '▴' : '▾'}
        </span>
      </button>

      {open ? (
        <div
          role="menu"
          aria-label={t('auth.profile')}
          className="panel absolute left-[var(--gap-tight)] right-[var(--gap-tight)] top-full z-40 mt-[var(--gap-hair)] overflow-hidden py-[var(--gap-hair)] shadow-lg"
        >
          {asking ? (
            <div className="px-[var(--gap)] py-[var(--gap-tight)]">
              <p className="text-[var(--text-small)]">{t('auth.signOutSure')}</p>
              <div className="mt-[var(--gap-tight)] flex flex-wrap gap-[var(--gap-tight)]">
                <button
                  type="button"
                  className="btn btn-quiet"
                  style={{ borderColor: 'var(--bad)', color: 'var(--bad)' }}
                  onClick={() => {
                    close();
                    void signOut();
                  }}
                >
                  {t('auth.signOut')}
                </button>
                <button type="button" className="btn btn-bare" onClick={() => setAsking(false)}>
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          ) : (
            <>
              <NavLink role="menuitem" to={MY_SEARCH} className={ITEM} onClick={close}>
                {t('auth.mySearch')}
                <span className="block text-[var(--text-micro)] text-[var(--ink-faint)]">
                  {t('auth.mySearchHint')}
                </span>
              </NavLink>
              <NavLink role="menuitem" to="/settings" className={ITEM} onClick={close}>
                {t('nav.settings')}
              </NavLink>
              <div className="rule-t my-[var(--gap-hair)]" />
              <button
                type="button"
                role="menuitem"
                className={ITEM}
                onClick={() => setAsking(true)}
              >
                {t('auth.signOut')}
              </button>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
