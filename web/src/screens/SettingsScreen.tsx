/**
 * Settings.
 *
 * Mostly a statement of where things are. That is deliberate: the promise the
 * app makes is that everything lives in files on this machine, and a settings
 * screen that shows the actual paths is how that promise is kept in view rather
 * than merely claimed in a README.
 *
 * One of those paths is not merely shown. The workbook is the file the user
 * actually opens, and until it could be moved from here the wizard's first
 * guess was permanent -- see `WorkbookSection`.
 */

import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { screenNumber } from '@/lib/screens';
import { formatWhen } from '@/lib/format';
import { LANGUAGES, setLanguage, type LanguageCode } from '@/i18n';
import { useTheme, type Theme } from '@/lib/useTheme';
import { Loading, Note, Problem, ScreenHeader, Section } from '@/components/primitives';
import AccountSection from '@/components/AccountSection';
import WorkbookSection from '@/components/WorkbookSection';

const THEMES: Theme[] = ['system', 'light', 'dark'];

function Fact({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rule-b grid grid-cols-[minmax(0,11rem)_1fr] items-baseline gap-[var(--gap)] py-[var(--gap-tight)] last:border-b-0">
      <dt className="eyebrow">{label}</dt>
      <dd
        className={`min-w-0 break-all text-[var(--text-small)] ${mono ? 'mono' : ''}`}
        style={{ margin: 0 }}
      >
        {value}
      </dd>
    </div>
  );
}

export default function SettingsScreen() {
  const { t, i18n } = useTranslation();
  const { theme, setTheme } = useTheme();

  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings });
  const sources = useQuery({ queryKey: ['sources'], queryFn: api.sources });

  if (settings.isLoading) return <Loading />;
  if (settings.error) {
    return <Problem message={String(settings.error)} onRetry={() => void settings.refetch()} />;
  }

  const data = settings.data!;

  return (
    <>
      <ScreenHeader
        number={screenNumber('settings')}
        title={t('settings.title')}
        lede={t('settings.lede')}
      />

      <Section label={t('settings.whereTitle')}>
        <dl className="panel px-[var(--gap-wide)] py-[var(--gap-tight)]">
          <Fact label={t('settings.home')} value={data.home} />
          <Fact label={t('settings.database')} value={data.database} />
          <Fact label={t('settings.backups')} value={data.backups} />
          <Fact
            label={t('settings.keepBackups')}
            value={String(data.keep_backups)}
            mono={false}
          />
        </dl>
      </Section>

      <WorkbookSection settings={data} />

      <AccountSection />

      <Section label={t('settings.appearance')}>
        <div className="grid gap-[var(--gap)] sm:grid-cols-2">
          <div>
            <p className="eyebrow mb-[var(--gap-tight)]">{t('common.language')}</p>
            <div className="flex gap-[var(--gap-tight)]">
              {LANGUAGES.map((language) => (
                <button
                  key={language.code}
                  type="button"
                  className="btn btn-quiet"
                  aria-pressed={i18n.language === language.code}
                  style={
                    i18n.language === language.code
                      ? { borderColor: 'var(--accent)', color: 'var(--accent)' }
                      : undefined
                  }
                  onClick={() => setLanguage(language.code as LanguageCode)}
                >
                  {language.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="eyebrow mb-[var(--gap-tight)]">{t('common.theme')}</p>
            <div className="flex gap-[var(--gap-tight)]">
              {THEMES.map((option) => (
                <button
                  key={option}
                  type="button"
                  className="btn btn-quiet"
                  aria-pressed={theme === option}
                  style={
                    theme === option
                      ? { borderColor: 'var(--accent)', color: 'var(--accent)' }
                      : undefined
                  }
                  onClick={() => setTheme(option)}
                >
                  {t(
                    `common.theme${option.charAt(0).toUpperCase()}${option.slice(1)}`,
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      </Section>

      <Section label={t('settings.sourcesTitle')} hint={t('settings.sourcesLede')}>
        <div className="panel scroll-x">
          <table className="w-full border-collapse text-[var(--text-small)]">
            <thead>
              <tr className="rule-b bg-[var(--ground-sunk)] text-left">
                <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)]">
                  {t('results.source')}
                </th>
                <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)]">
                  {t('results.status')}
                </th>
                <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)] text-right">
                  {t('common.jobs', { count: 0 }).replace(/^\d+\s*/, '')}
                </th>
              </tr>
            </thead>
            <tbody>
              {(sources.data?.sources ?? []).map((source) => {
                const health = source.health;
                const failing = Boolean(health?.last_error && !health?.last_ok);
                return (
                  <tr key={source.id} className="rule-b last:border-b-0">
                    <td className="px-[var(--gap)] py-[var(--gap-tight)]">
                      <a
                        href={source.homepage}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="font-medium hover:text-[var(--accent)] hover:underline"
                      >
                        {source.name}
                      </a>
                      <span className="mono ml-[var(--gap-tight)] text-[var(--text-micro)] text-[var(--ink-faint)]">
                        {source.id}
                      </span>
                    </td>
                    <td
                      className="px-[var(--gap)] py-[var(--gap-tight)] text-[var(--text-micro)]"
                      style={{
                        color: !health
                          ? 'var(--ink-faint)'
                          : failing
                            ? 'var(--bad)'
                            : 'var(--ok)',
                      }}
                    >
                      {!health
                        ? t('settings.never')
                        : failing
                          ? t('search.healthBad', {
                              when: formatWhen(health.last_error, i18n.language),
                            })
                          : t('search.healthOk', {
                              when: formatWhen(health.last_ok, i18n.language),
                            })}
                      {health?.message ? (
                        <span className="block text-[var(--ink-faint)]">{health.message}</span>
                      ) : null}
                    </td>
                    <td className="mono px-[var(--gap)] py-[var(--gap-tight)] text-right text-[var(--text-micro)] text-[var(--ink-faint)]">
                      {health?.last_count ?? '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="mt-[var(--gap)]">
          <Note tone="ok">
            <strong className="block">{t('settings.fairPlay')}</strong>
            {t('settings.fairPlayText')}
          </Note>
        </div>
      </Section>

      <Section label={t('settings.about')}>
        <dl className="panel px-[var(--gap-wide)] py-[var(--gap-tight)]">
          <Fact label={t('settings.version')} value={data.version} />
          <Fact label={t('settings.python')} value={data.python} />
          <Fact label={t('settings.platform')} value={data.platform} />
          <Fact
            label={t('settings.sourcesInstalled')}
            value={String(data.sources_installed)}
          />
        </dl>
      </Section>
    </>
  );
}
