/**
 * The hallway: eight questions between signing in and searching.
 *
 * It exists because the search screen is a poor first impression. Everything on
 * it is optional, nothing on it is explained, and a person who has just made an
 * account is looking at three dozen controls with no idea which two matter. The
 * wizard asks the same questions one at a time, in the order a person can
 * answer them, and writes the answers down as the account's setup -- which the
 * search screen then opens with, already filled in.
 *
 * It is a wall, not a suggestion: the account is not marked as onboarded until
 * the last step, and until it is, this is what signing in leads to. That is a
 * deliberate trade. Somebody who wanted to skip it loses a minute; somebody who
 * would have bounced off an empty search screen gets a search that runs.
 *
 * One thing is required at the end and only one: a source. Everything else has
 * a working default, but a search with nowhere to look is not a search, and
 * finding that out on the next screen would make the wizard a waste of a minute
 * rather than the saving of one.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';

import { api, ApiError } from '@/lib/api';
import { useAccount } from '@/lib/account';
import { EMPTY_SETUP, type Account, type SearchProfile, type SearchSetup } from '@/lib/types';
import LanguagePicker from '@/components/LanguagePicker';
import {
  StepExclusions,
  StepFinePrint,
  StepFreshness,
  StepHeadline,
  StepKeywords,
  StepSources,
  StepWhere,
  StepWorkbook,
  type StepProps,
} from '@/components/SetupSteps';

const STEPS = [
  'headline',
  'keywords',
  'where',
  'freshness',
  'no',
  'fine',
  'sources',
  'workbook',
] as const;

export default function WelcomeScreen() {
  const { t, i18n } = useTranslation();
  const { account, adopt, signOut } = useAccount();

  const [step, setStep] = useState(0);
  const [setup, setSetup] = useState<SearchSetup>(() => ({
    ...EMPTY_SETUP,
    // One empty group waiting rather than an empty list and a button: the
    // question is "what words describe the job", and a blank field asks it.
    profile: { ...EMPTY_SETUP.profile, keyword_groups: [{ name: '', terms: [] }] },
  }));
  const [workbook, setWorkbook] = useState('');

  const sources = useQuery({ queryKey: ['sources'], queryFn: api.sources });
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings });

  const onChange = (patch: Partial<SearchSetup>) =>
    setSetup((current) => ({ ...current, ...patch }));
  const onProfile = (patch: Partial<SearchProfile>) =>
    setSetup((current) => ({ ...current, profile: { ...current.profile, ...patch } }));

  const finish = useMutation<Account, Error, void>({
    mutationFn: () =>
      api.auth.finishOnboarding(
        {
          ...setup,
          headline: setup.headline.trim(),
          // Half-typed groups are dropped rather than saved: a group with a
          // name and no words matches nothing, and one with words and no name
          // would put an empty category in the spreadsheet.
          profile: {
            ...setup.profile,
            keyword_groups: setup.profile.keyword_groups.filter(
              (group) => group.name.trim() && group.terms.length,
            ),
          },
        },
        workbook.trim(),
      ),
    onSuccess: adopt,
  });

  const name = STEPS[step] ?? 'headline';
  const last = step === STEPS.length - 1;
  const canFinish = setup.sources.length > 0;

  const stepProps: StepProps = { setup, onChange, onProfile };

  const failure = finish.error;
  const problem = useMemo(() => {
    if (!failure) return '';
    if (failure instanceof ApiError) {
      return t(`auth.errors.${failure.code}`, { defaultValue: failure.message });
    }
    return t('error.generic');
  }, [failure, t]);

  return (
    <div className="min-h-dvh bg-[var(--ground-sunk)] px-[var(--gap-wide)] py-[var(--gap-wide)]">
      <div className="mx-auto w-full max-w-[52rem]">
        <header className="rule-b flex flex-wrap items-end justify-between gap-[var(--gap)] pb-[var(--gap)]">
          <div>
            <p className="text-[1.35rem] font-bold leading-none tracking-[-0.035em]">
              Job<span className="text-[var(--accent)]">Sheet</span>
            </p>
            <p className="mt-[var(--gap-hair)] text-[var(--text-small)] text-[var(--ink-soft)]">
              {t('welcome.greeting', { name: account?.username ?? '' })}
            </p>
          </div>
          <button type="button" className="btn btn-bare" onClick={() => void signOut()}>
            {t('auth.signOut')}
          </button>
        </header>

        {/* The whole path, always visible. Eight unnumbered screens feel
            endless; eight numbered ones with the last in sight do not. */}
        <ol className="scroll-x mt-[var(--gap)] flex gap-[var(--gap-tight)]">
          {STEPS.map((key, index) => (
            <li key={key} className="shrink-0">
              <button
                type="button"
                className="btn btn-bare px-[0.35rem] text-[var(--text-micro)]"
                aria-current={index === step ? 'step' : undefined}
                // Backwards only. Jumping ahead would let somebody reach the
                // finish before the question that decides whether they can.
                disabled={index > step}
                onClick={() => setStep(index)}
                style={{
                  color:
                    index === step
                      ? 'var(--accent)'
                      : index < step
                        ? 'var(--ink-soft)'
                        : 'var(--ink-faint)',
                  fontWeight: index === step ? 700 : 500,
                }}
              >
                <span className="mono">{String(index + 1).padStart(2, '0')}</span>{' '}
                {t(`welcome.${key}.step`)}
              </button>
            </li>
          ))}
        </ol>

        <main className="panel mt-[var(--gap)] p-[var(--gap-wide)]">
          <p className="eyebrow mono mb-[var(--gap-tight)]">
            {String(step + 1).padStart(2, '0')} / {STEPS.length}
          </p>
          <h1 style={{ fontSize: 'var(--text-title)' }}>{t(`welcome.${name}.title`)}</h1>
          <p className="mt-[var(--gap-tight)] max-w-[62ch] text-[var(--text-small)] text-[var(--ink-soft)]">
            {t(`welcome.${name}.lede`)}
          </p>

          <div className="mt-[var(--gap-wide)]">
            {name === 'headline' ? <StepHeadline {...stepProps} /> : null}
            {name === 'keywords' ? <StepKeywords {...stepProps} /> : null}
            {name === 'where' ? <StepWhere {...stepProps} /> : null}
            {name === 'freshness' ? <StepFreshness {...stepProps} /> : null}
            {name === 'no' ? <StepExclusions {...stepProps} /> : null}
            {name === 'fine' ? <StepFinePrint {...stepProps} /> : null}
            {name === 'sources' ? (
              <StepSources
                {...stepProps}
                sources={sources.data?.sources ?? []}
                loading={sources.isPending}
                error={sources.error ? t('error.generic') : ''}
                onRetry={() => void sources.refetch()}
                locale={i18n.language}
              />
            ) : null}
            {name === 'workbook' ? (
              <StepWorkbook
                setup={setup}
                workbook={workbook}
                onWorkbook={setWorkbook}
                defaultPath={settings.data?.workbook ?? ''}
                problem={problem}
              />
            ) : null}
          </div>

          {last && !canFinish ? (
            <p
              className="mt-[var(--gap-wide)] border-l-[3px] pl-[var(--gap-tight)] text-[var(--text-small)]"
              style={{ borderLeftColor: 'var(--warn)' }}
            >
              {t('welcome.needSource')}
            </p>
          ) : null}

          <div className="rule-t mt-[var(--gap-section)] flex items-center justify-between gap-[var(--gap)] pt-[var(--gap)]">
            <button
              type="button"
              className="btn btn-quiet"
              disabled={step === 0}
              onClick={() => setStep((current) => Math.max(0, current - 1))}
            >
              {t('welcome.back')}
            </button>

            {last ? (
              <button
                type="button"
                className="btn btn-primary"
                disabled={!canFinish || finish.isPending}
                onClick={() => finish.mutate()}
              >
                {finish.isPending ? t('auth.working') : t('welcome.finish')}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setStep((current) => Math.min(STEPS.length - 1, current + 1))}
              >
                {t('welcome.next')}
              </button>
            )}
          </div>
        </main>

        <LanguagePicker className="mt-[var(--gap-wide)]" />
      </div>
    </div>
  );
}
