/**
 * Language and theme, in one small row.
 *
 * It lives in two places -- the rail, and the sign-in screen -- and the second
 * one is why it is a component rather than markup in the rail. Somebody whose
 * Croatian browser did not announce itself, or who shares a laptop with an
 * English speaker, has to be able to switch *before* they can sign in. A
 * language control locked behind the door is no use to the person outside it.
 */

import { useTranslation } from 'react-i18next';

import { useTheme } from '@/lib/useTheme';
import { LANGUAGES, setLanguage, type LanguageCode } from '@/i18n';

export default function LanguagePicker({ className = '' }: { className?: string }) {
  const { t, i18n } = useTranslation();
  const { theme, cycle } = useTheme();

  return (
    <div className={`flex items-center justify-between gap-[var(--gap)] ${className}`}>
      <div className="flex gap-[var(--gap-hair)]">
        {LANGUAGES.map((language) => (
          <button
            key={language.code}
            type="button"
            className="btn btn-bare mono text-[var(--text-micro)] uppercase"
            aria-pressed={i18n.language === language.code}
            style={{
              color: i18n.language === language.code ? 'var(--accent)' : 'var(--ink-faint)',
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
  );
}
