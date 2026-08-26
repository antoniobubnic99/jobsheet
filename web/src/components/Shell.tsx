/**
 * The frame: a left rail, a content column, nothing else.
 *
 * Few enough screens that they can all be visible at once, which is better than
 * a menu -- the user can see the whole app and never has to remember where
 * anything lives. The rail carries a number, a name and a one-line hint, so the
 * app explains itself without a tour.
 */

import { NavLink, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useAccount } from '@/lib/account';
import LanguagePicker from '@/components/LanguagePicker';

/**
 * Screens kept out of the rail.
 *
 * Hidden, not removed: the route still resolves, so `/designer` works if you
 * type it or follow a link, and nothing that depends on a layout stops working.
 * The sheet designer is a thing you use once, when you decide what the workbook
 * should look like; after that it is a door you walk past every day and never
 * open. The workbook carries its own layout, so the design survives without it.
 *
 * Take a key out of this list to put the screen back in the rail. Numbering
 * below is computed, so the rail stays 01, 02, 03… with no gap where this was.
 */
const HIDDEN_FROM_RAIL: readonly string[] = ['designer'];

const ALL_SCREENS = [
  { to: '/', key: 'search', end: true },
  { to: '/results', key: 'results', end: false },
  { to: '/designer', key: 'designer', end: false },
  { to: '/tracker', key: 'tracker', end: false },
  { to: '/settings', key: 'settings', end: false },
] as const;

const SCREENS = ALL_SCREENS.filter((screen) => !HIDDEN_FROM_RAIL.includes(screen.key)).map(
  (screen, index) => ({ ...screen, number: String(index + 1).padStart(2, '0') }),
);

export default function Shell() {
  const { t } = useTranslation();
  const { account, signOut } = useAccount();

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[var(--rail-width)_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:bg-[var(--surface)] focus:px-3 focus:py-2"
      >
        Skip to content
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

          {/* A strip on a phone, a column on a desktop. The items must not
              shrink into each other on the strip, hence `shrink-0`. */}
          <ul className="scroll-x flex flex-1 flex-row md:flex-col md:overflow-visible">
            {SCREENS.map((screen) => (
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

          {/* Whose search this is. Not decoration: one install can hold several,
              and the only thing standing between "my applications" and
              somebody else's is knowing which account is open. */}
          <div className="rule-t hidden px-[var(--gap-wide)] py-[var(--gap)] md:block">
            <p className="text-[var(--text-small)] font-semibold">{account?.username}</p>
            <button
              type="button"
              className="btn btn-bare px-0 text-[var(--text-micro)] text-[var(--ink-faint)]"
              onClick={() => void signOut()}
            >
              {t('auth.signOut')}
            </button>
          </div>

          <LanguagePicker className="rule-t hidden px-[var(--gap-wide)] py-[var(--gap)] md:flex" />
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
