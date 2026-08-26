/**
 * The front page: what JobSheet is, before anybody has typed anything.
 *
 * It exists because the door asked for a username without ever saying what the
 * username was for. Somebody opening this for the first time -- or looking over
 * a shoulder at it -- should be able to read what the thing does, see roughly
 * what comes out of it, and then choose between the two doors.
 *
 * Two claims on this page are load-bearing and neither is decoration:
 *
 * * **The sample sheet** is the product. It is drawn rather than described,
 *   because "you get a spreadsheet" and a picture of one land differently. It
 *   is `aria-hidden`, and the prose beside it says the same thing in words --
 *   a screen reader gets the sentence, not a table of made-up jobs.
 * * **The source list is real.** It comes from the door's own status call, so
 *   it can never promise a source this install does not have. Install a source
 *   plugin and the front page says so, with nothing edited here.
 *
 * Which action is offered first depends on the install, exactly as the door
 * does: an install holding a search from before accounts offers to hand it
 * over, and one with no accounts at all does not offer a sign-in nobody could
 * complete.
 */

import { useTranslation } from 'react-i18next';

import type { AuthStatus } from '@/lib/types';
import LanguagePicker from '@/components/LanguagePicker';

const REPO = 'https://github.com/antoniobubnic99/jobsheet';

const STEPS = ['one', 'two', 'three'] as const;
const PROMISES = ['sheet', 'tracker', 'letter', 'local'] as const;
const SAMPLE_ROWS = ['one', 'two', 'three'] as const;

export default function LandingScreen({
  status,
  onStart,
  onSignIn,
}: {
  /** What the door knows. Absent while it is still being asked. */
  status: AuthStatus | undefined;
  onStart: () => void;
  onSignIn: () => void;
}) {
  const { t } = useTranslation();

  const claimable = status?.claimable ?? null;
  // Undefined means the question has not been answered yet. Hiding sign-in on
  // that basis would blink it in a moment later, so only a definite zero hides
  // it -- and a definite zero means there is genuinely nothing to sign into.
  const nothingToSignInto = status?.accounts === 0;
  const sources = status?.sources;
  const version = window.__JOBSHEET__?.version ?? '';

  return (
    <div className="min-h-dvh bg-[var(--ground)]">
      <header className="rule-b">
        <div className="mx-auto flex max-w-[68rem] items-center justify-between gap-[var(--gap)] px-[var(--gap-wide)] py-[var(--gap)]">
          <p className="text-[1.35rem] font-bold leading-none tracking-[-0.035em]">
            Job<span className="text-[var(--accent)]">Sheet</span>
          </p>
          <LanguagePicker className="w-[9rem]" />
        </div>
      </header>

      <main className="mx-auto w-full max-w-[68rem] px-[var(--gap-wide)] pb-[var(--gap-section)]">
        {/* ---------------------------------------------------------- hero */}
        <section className="grid items-start gap-[var(--gap-section)] py-[var(--gap-section)] lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <p className="eyebrow mono">{t('landing.eyebrow')}</p>
            <h1
              className="mt-[var(--gap)] max-w-[18ch]"
              style={{ fontSize: 'var(--text-display)', letterSpacing: '-0.03em' }}
            >
              {t('landing.headline')}
            </h1>
            <p className="mt-[var(--gap-wide)] max-w-[52ch] text-[var(--text-lead)] leading-relaxed text-[var(--ink-soft)]">
              {t('landing.lede')}
            </p>

            <div className="mt-[var(--gap-wide)] flex flex-wrap items-center gap-[var(--gap-tight)]">
              <button
                type="button"
                className="btn btn-primary px-[var(--gap-wide)] py-[0.6rem] text-[var(--text-body)]"
                onClick={onStart}
              >
                {claimable ? t('landing.startClaim') : t('landing.start')}
              </button>
              {nothingToSignInto ? null : (
                <button
                  type="button"
                  className="btn btn-quiet px-[var(--gap-wide)] py-[0.6rem] text-[var(--text-body)]"
                  onClick={onSignIn}
                >
                  {t('landing.signIn')}
                </button>
              )}
            </div>

            <p className="mt-[var(--gap)] max-w-[44ch] text-[var(--text-small)] leading-snug text-[var(--ink-faint)]">
              {t('landing.privacy')}
            </p>

            {claimable ? (
              <p
                className="panel mt-[var(--gap-wide)] max-w-[46ch] border-l-[3px] px-[var(--gap)] py-[var(--gap-tight)] text-[var(--text-small)]"
                style={{ borderLeftColor: 'var(--accent)' }}
              >
                {t('landing.claimNote')}
              </p>
            ) : null}
          </div>

          <SampleSheet />
        </section>

        {/* ------------------------------------------------------ 01 how it works */}
        <section className="rule-t pt-[var(--gap-wide)]">
          <h2 className="eyebrow">
            <span className="mono mr-[var(--gap-tight)]">01</span>
            {t('landing.how.label')}
          </h2>
          <ol className="mt-[var(--gap-wide)] grid gap-[var(--gap-wide)] md:grid-cols-3">
            {STEPS.map((step, index) => (
              <li
                key={step}
                className="border-t border-[var(--rule)] pt-[var(--gap)] md:border-l md:border-t-0 md:pl-[var(--gap-wide)] md:pt-0 md:first:border-l-0 md:first:pl-0"
              >
                <p className="mono text-[var(--text-small)] font-semibold text-[var(--accent)]">
                  {String(index + 1).padStart(2, '0')}
                </p>
                <h3 className="mt-[var(--gap-tight)] text-[var(--text-lead)]">
                  {t(`landing.how.${step}.title`)}
                </h3>
                <p className="mt-[var(--gap-tight)] text-[var(--text-small)] leading-relaxed text-[var(--ink-soft)]">
                  {t(`landing.how.${step}.body`)}
                </p>
              </li>
            ))}
          </ol>
        </section>

        {/* ------------------------------------------------- 02 what you get */}
        <section className="mt-[var(--gap-section)] rule-t pt-[var(--gap-wide)]">
          <h2 className="eyebrow">
            <span className="mono mr-[var(--gap-tight)]">02</span>
            {t('landing.what.label')}
          </h2>
          <div className="mt-[var(--gap-wide)] grid gap-[var(--gap)] sm:grid-cols-2">
            {PROMISES.map((promise) => (
              <div key={promise} className="panel p-[var(--gap-wide)]">
                <h3 className="text-[var(--text-lead)]">{t(`landing.what.${promise}.title`)}</h3>
                <p className="mt-[var(--gap-tight)] text-[var(--text-small)] leading-relaxed text-[var(--ink-soft)]">
                  {t(`landing.what.${promise}.body`)}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* -------------------------------------------------- 03 the sources */}
        <section className="mt-[var(--gap-section)] rule-t pt-[var(--gap-wide)]">
          <h2 className="eyebrow">
            <span className="mono mr-[var(--gap-tight)]">03</span>
            {t('landing.sources.label')}
          </h2>
          <p className="mt-[var(--gap-tight)] max-w-[62ch] text-[var(--text-small)] leading-relaxed text-[var(--ink-soft)]">
            {t('landing.sources.hint')}
          </p>

          {sources && sources.names.length ? (
            <>
              <p className="mono mt-[var(--gap)] text-[var(--text-small)] text-[var(--ink-faint)]">
                {t('landing.sources.count', { count: sources.count })}
              </p>
              <ul className="mt-[var(--gap-tight)] flex flex-wrap gap-[var(--gap-hair)]">
                {sources.names.map((name) => (
                  <li
                    key={name}
                    className="mono rounded-[var(--radius-sharp)] bg-[var(--ground-sunk)] px-[0.5rem] py-[0.15rem] text-[var(--text-small)] text-[var(--ink-soft)]"
                    style={{ border: '1px solid var(--rule)' }}
                  >
                    {name}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-[var(--gap)] text-[var(--text-small)] text-[var(--ink-faint)]">
              {t('landing.sources.unknown')}
            </p>
          )}
        </section>

        {/* ------------------------------------------------------- closing */}
        <section className="mt-[var(--gap-section)] panel flex flex-wrap items-center justify-between gap-[var(--gap-wide)] p-[var(--gap-wide)]">
          <div className="max-w-[46ch]">
            <h2 style={{ fontSize: 'var(--text-title)' }}>{t('landing.closing.title')}</h2>
            <p className="mt-[var(--gap-tight)] text-[var(--text-small)] text-[var(--ink-soft)]">
              {t('landing.closing.body')}
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary px-[var(--gap-wide)] py-[0.6rem] text-[var(--text-body)]"
            onClick={onStart}
          >
            {claimable ? t('landing.startClaim') : t('landing.start')}
          </button>
        </section>

        <footer className="mono mt-[var(--gap-wide)] flex flex-wrap items-center justify-between gap-[var(--gap-tight)] text-[var(--text-micro)] text-[var(--ink-faint)]">
          <span>{version ? t('landing.version', { version }) : 'JobSheet'}</span>
          <a href={REPO} target="_blank" rel="noreferrer" className="underline">
            {t('landing.repo')}
          </a>
        </footer>
      </main>
    </div>
  );
}

/**
 * A few rows of the thing this app produces.
 *
 * Hairlines, tabular numbers and a mono header: the same grammar the results
 * table uses, so the promise and the product look like each other. Hidden from
 * assistive technology on purpose -- these are illustrative jobs, and reading
 * three invented rows aloud would be worse than reading the sentence above.
 */
function SampleSheet() {
  const { t } = useTranslation();

  return (
    <figure className="m-0">
      <div className="panel overflow-hidden" aria-hidden>
        <div className="rule-b flex items-center gap-[var(--gap-hair)] bg-[var(--ground-sunk)] px-[var(--gap)] py-[var(--gap-tight)]">
          <span className="mono text-[var(--text-micro)] text-[var(--ink-faint)]">jobs.xlsx</span>
        </div>
        <div className="scroll-x">
          <table className="tabular w-full border-collapse text-[var(--text-small)]">
          <thead>
            <tr className="rule-b">
              {(['position', 'company', 'place'] as const).map((column) => (
                <th
                  key={column}
                  className="eyebrow px-[var(--gap)] py-[var(--gap-tight)] text-left font-semibold"
                >
                  {t(`landing.sample.${column}`)}
                </th>
              ))}
              <th className="eyebrow px-[var(--gap)] py-[var(--gap-tight)] text-right font-semibold">
                {t('landing.sample.applied')}
              </th>
            </tr>
          </thead>
          <tbody>
            {SAMPLE_ROWS.map((row, index) => (
              <tr key={row} className={index === 0 ? 'bg-[var(--accent-soft)]' : undefined}>
                <td className="rule-t px-[var(--gap)] py-[var(--gap-tight)] font-medium">
                  {t(`landing.sample.${row}.position`)}
                </td>
                <td className="rule-t px-[var(--gap)] py-[var(--gap-tight)] text-[var(--ink-soft)]">
                  {t(`landing.sample.${row}.company`)}
                </td>
                <td className="rule-t px-[var(--gap)] py-[var(--gap-tight)] text-[var(--ink-soft)]">
                  {t(`landing.sample.${row}.place`)}
                </td>
                <td className="rule-t px-[var(--gap)] py-[var(--gap-tight)] text-right">
                  {/* A drawn checkbox rather than a real one: the sheet is a
                      picture, and an input here would invite a click that does
                      nothing. */}
                  <span
                    className="inline-grid h-[0.95rem] w-[0.95rem] place-items-center rounded-[var(--radius-sharp)] text-[0.7rem] leading-none"
                    style={{
                      border: '1px solid var(--rule-strong)',
                      background: index === 0 ? 'var(--accent)' : 'var(--surface)',
                      color: 'var(--accent-ink)',
                    }}
                  >
                    {index === 0 ? '✓' : ''}
                  </span>
                </td>
              </tr>
            ))}
            </tbody>
          </table>
        </div>
      </div>
      <figcaption className="mt-[var(--gap-tight)] text-[var(--text-micro)] text-[var(--ink-faint)]">
        {t('landing.sample.label')}
      </figcaption>
    </figure>
  );
}
