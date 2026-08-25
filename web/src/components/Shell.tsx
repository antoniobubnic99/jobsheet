/**
 * The frame: a left rail, a content column, nothing else.
 *
 * Five screens is few enough that they can all be visible all the time, which
 * is better than a menu -- the user can see the whole app at once and never has
 * to remember where anything lives. The rail carries a number, a name and a
 * one-line hint, so the app explains itself without a tour.
 */

import { NavLink, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { useTheme } from '@/lib/useTheme';
import { LANGUAGES, setLanguage, type LanguageCode } from '@/i18n';

const SCREENS = [
  { to: '/', key: 'search', number: '01', end: true },
  { to: '/results', key: 'results', number: '02', end: false },
  { to: '/designer', key: 'designer', number: '03', end: false },
  { to: '/tracker', key: 'tracker', number: '04', end: false },
  { to: '/settings', key: 'settings', number: '05', end: false },
] as const;

export default function Shell() {
  const { t, i18n } = useTranslation();
  const { theme, cycle } = useTheme();

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

          <div className="rule-t hidden items-center justify-between px-[var(--gap-wide)] py-[var(--gap)] md:flex">
            <div className="flex gap-[var(--gap-hair)]">
              {LANGUAGES.map((language) => (
                <button
                  key={language.code}
                  type="button"
                  className="btn btn-bare mono text-[var(--text-micro)] uppercase"
                  aria-pressed={i18n.language === language.code}
                  style={{
                    color:
                      i18n.language === language.code ? 'var(--accent)' : 'var(--ink-faint)',
                    fontWeight: i18n.language === language.code ? 700 : 500,
                  }}
                  onClick={() => setLanguage(language.code as LanguageCode)}
                >
                  {language.code}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn btn-bare text-[var(--text-micro)]"
              onClick={cycle}
              aria-label={t('common.theme')}
              title={t('common.theme')}
            >
              {theme === 'light' ? '☀' : theme === 'dark' ? '☾' : '◐'}
            </button>
          </div>
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
