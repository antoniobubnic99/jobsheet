/**
 * The frame: a left rail, a content column, nothing else.
 *
 * Few enough screens that they can all be visible at once, which is better than
 * a menu -- the user can see the whole app and never has to remember where
 * anything lives. The rail carries a number, a name and a one-line hint, so the
 * app explains itself without a tour.
 *
 * The one thing that *is* a menu is the account, and it sits at the top of the
 * rail at every width. It used to be a name and a sign-out link pinned to the
 * bottom behind `hidden md:block`: on a phone the app would not say whose
 * search you were reading and offered no way out of it. The screen list, the
 * account and the language switch are now all reachable on a 375px screen,
 * because that is the width the person checking their applications on the bus
 * is actually holding.
 *
 * The numbering comes from `lib/screens`, not from here. It has to: the rail
 * and each screen's own heading both print it, and they disagreed the moment a
 * screen was hidden from the rail.
 */

import { useEffect } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { RAIL_SCREENS } from '@/lib/screens';
import LanguagePicker from '@/components/LanguagePicker';
import ProfileMenu from '@/components/ProfileMenu';

export default function Shell() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();

  // A fresh load always opens on Home, whatever address was in the bar --
  // reopening the app is not the same as picking up where you left off.
  // The empty dependency list is the point: this must fire once, when the
  // shell first appears, and never again on a re-render the session's own
  // window-focus refetch causes while the person is mid-task somewhere else
  // in the rail.
  useEffect(() => {
    if (location.pathname !== '/') navigate('/', { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[var(--rail-width)_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-[var(--surface)] focus:px-3 focus:py-2"
      >
        {t('app.skipToContent')}
      </a>

      <nav
        aria-label={t('app.name')}
        className="rule-b bg-[var(--ground-sunk)] md:sticky md:top-0 md:h-dvh md:border-b-0 md:border-r md:border-[var(--rule)]"
      >
        <div className="flex h-full flex-col">
          <div className="px-[var(--gap-wide)] pb-[var(--gap-wide)] pt-[var(--gap-wide)]">
            {/* The wordmark is set tight and heavy against the airy rail: the
                one place in the interface with real display weight. */}
            <p className="text-[1.35rem] font-bold leading-none tracking-[-0.035em]">
              Job<span className="text-[var(--accent)]">Sheet</span>
            </p>
            <p className="mt-[var(--gap-tight)] max-w-[22ch] text-[var(--text-micro)] leading-snug text-[var(--ink-faint)]">
              {t('app.tagline')}
            </p>
          </div>

          <ProfileMenu className="rule-t rule-b" />

          {/* A strip on a phone, a column on a desktop. The items must not
              shrink into each other on the strip, hence `shrink-0`. */}
          <ul className="scroll-x flex flex-1 flex-row md:flex-col md:overflow-visible">
            {RAIL_SCREENS.map((screen) => (
              <li key={screen.to} className="shrink-0 md:rule-t">
                <NavLink
                  to={screen.to}
                  end={screen.end}
                  className={({ isActive }) =>
                    [
                      'group flex items-baseline gap-[var(--gap-tight)] whitespace-nowrap px-[var(--gap)] py-[var(--gap)] transition-colors md:whitespace-normal md:px-[var(--gap-wide)]',
                      'border-b-[3px] md:border-b-0 md:border-l-[3px]',
                      isActive
                        ? 'border-[var(--accent)] bg-[var(--surface)]'
                        : 'border-transparent hover:bg-[var(--surface)]',
                    ].join(' ')
                  }
                >
                  {({ isActive }) => (
                    <>
                      <span
                        className="mono text-[var(--text-micro)]"
                        style={{ color: isActive ? 'var(--accent)' : 'var(--ink-faint)' }}
                      >
                        {screen.number}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-[var(--text-small)] font-semibold">
                          {t(`nav.${screen.key}`)}
                        </span>
                        <span className="hidden text-[var(--text-micro)] leading-snug text-[var(--ink-faint)] md:block">
                          {t(`nav.${screen.key}Hint`)}
                        </span>
                      </span>
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>

          <LanguagePicker className="rule-t flex px-[var(--gap-wide)] py-[var(--gap)]" />
        </div>
      </nav>

      <main
        id="main"
        className="mx-auto w-full max-w-[78rem] px-[var(--gap-wide)] pb-[var(--gap-section)] pt-[var(--gap-wide)] md:px-[var(--gap-section)]"
      >
        <Outlet />
      </main>
    </div>
  );
}
