/**
 * The hallway: seven questions between signing in and searching.
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
 *
 * ## Why the answers are written to `sessionStorage`
 *
 * This component held everything in `useState` and nothing else, and `Gate`
 * swaps the component out whenever `auth/me` answers 401 or the server pauses
 * long enough to look like it has. When that happened the wizard was unmounted
 * and four screens of typing went with it, with no error and nothing to click.
 * A draft written on every keystroke and cleared on a successful finish costs
 * one line per change and removes the whole failure.
 *
 * `sessionStorage` and not `localStorage`, deliberately: a half-finished wizard
 * should survive a remount and a refresh, and should not still be waiting a week
 * later on a tab somebody opens by accident.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';

import { api, ApiError } from '@/lib/api';
import { useAccount } from '@/lib/account';
import { EMPTY_SETUP, type Account, type SearchProfile, type SearchSetup } from '@/lib/types';
import LanguagePicker from '@/components/LanguagePicker';
import {
  StepEmployers,
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
  'employers',
  'sources',
  'workbook',
] as const;

/**
 * Where the half-finished wizard is kept, per account.
 *
 * Per account and not one key for the whole install: two people share this
 * laptop, and the second one to sit down should get the wizard, not the first
 * one's half-typed answers.
 */
const draftKey = (id: number | undefined) => `jobsheet.wizard.draft.${id ?? 'new'}`;

/**
 * The same comparison `jobsheet.core.matching.fold` makes on the server.
 *
 * Only ever used to line a county the user typed up against the list, never to
 * decide anything: a name that does not match simply pre-selects nothing.
 */
const fold = (text: string) =>
  text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[đĐ]/g, 'd')
    .toLowerCase()
    .replace(/zupanija/, '')
    .trim();

interface Draft {
  step: number;
  setup: SearchSetup;
  workbook: string;
}

/** One empty group waiting: the question is "what words", and a blank field asks it. */
const FRESH: SearchSetup = {
  ...EMPTY_SETUP,
  profile: { ...EMPTY_SETUP.profile, keyword_groups: [{ name: '', terms: [] }] },
};

function readDraft(key: string): Draft | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const saved = JSON.parse(raw) as Partial<Draft>;
    if (!saved.setup?.profile) return null;
    // Merged over the current empty shapes rather than trusted as-is: a draft
    // written before a field existed would otherwise arrive without it and the
    // step that reads it would crash on the first render.
    return {
      step: Math.min(Math.max(0, saved.step ?? 0), STEPS.length - 1),
      workbook: saved.workbook ?? '',
      setup: {
        ...FRESH,
        ...saved.setup,
        profile: { ...FRESH.profile, ...saved.setup.profile },
      },
    };
  } catch {
    // A private window, or storage the browser refuses. The wizard still works;
    // it just forgets, which is what it did before this existed.
    return null;
  }
}

export default function WelcomeScreen() {
  const { t, i18n } = useTranslation();
  const { account, adopt, signOut } = useAccount();

  // Read once, on the first render. Re-reading later would fight the state it
  // was used to seed: the draft is written from that state on every change.
  const key = draftKey(account?.id);
  const restored = useMemo(() => readDraft(key), [key]);
  const [step, setStep] = useState(restored?.step ?? 0);
  const [setup, setSetup] = useState<SearchSetup>(restored?.setup ?? FRESH);
  const [workbook, setWorkbook] = useState(restored?.workbook ?? '');

  const sources = useQuery({ queryKey: ['sources'], queryFn: api.sources });
  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings });

  useEffect(() => {
    try {
      sessionStorage.setItem(key, JSON.stringify({ step, setup, workbook }));
    } catch {
      // Out of quota or storage disabled. Losing the draft is survivable;
      // taking the wizard down over it is not.
    }
  }, [key, step, setup, workbook]);

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
          // would put an empty category in the spreadsheet. The keywords step
          // says so while there is still something to be done about it.
          profile: {
            ...setup.profile,
            keyword_groups: setup.profile.keyword_groups.filter(
              (group) => group.name.trim() && group.terms.length,
            ),
          },
        },
        workbook.trim(),
      ),
    onSuccess: (saved) => {
      try {
        sessionStorage.removeItem(key);
      } catch {
        // Nothing to clean up if storage was never available.
      }
      adopt(saved);
    },
  });

  const name = STEPS[step] ?? 'headline';
  const last = step === STEPS.length - 1;
  const canFinish = setup.sources.length > 0;

  const stepProps: StepProps = { setup, onChange, onProfile };

  /**
   * The employment-service feeds implied by the counties named on step 3.
   *
   * Somebody who has said they want to work in Istra should not then have to
   * find Istarska in a list of twenty-one on the sources step. The mapping from
   * a county name to a feed number already exists on the server -- it is what
   * the region picker was drawing from -- so this is only a matter of not
   * throwing the answer away between two screens.
   */
  const counties = useQuery({
    queryKey: ['places', 'county'],
    queryFn: () => api.places('', 'county'),
    staleTime: Infinity,
  });

  const countyFeeds = useMemo(() => {
    const byName = new Map(
      (counties.data?.counties ?? []).map((one) => [fold(one.name), one.feed]),
    );
    return setup.profile.regions
      .map((region) => byName.get(fold(region)))
      .filter((feed): feed is number => typeof feed === 'number');
  }, [counties.data, setup.profile.regions]);

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

        {/* The whole path, always visible. Seven unnumbered screens feel
            endless; seven numbered ones with the last in sight do not. */}
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
            {name === 'employers' ? <StepEmployers {...stepProps} /> : null}
            {name === 'sources' ? (
              <StepSources
                {...stepProps}
                sources={sources.data?.sources ?? []}
                countries={sources.data?.countries ?? []}
                loading={sources.isPending}
                error={sources.error ? t('error.generic') : ''}
                onRetry={() => void sources.refetch()}
                locale={i18n.language}
                countyFeeds={countyFeeds}
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
