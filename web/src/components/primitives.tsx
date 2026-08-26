/**
 * The pieces every screen is built from.
 *
 * Small on purpose: each one exists because the same arrangement appeared
 * three times, not because a design system was planned in advance.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { ApplicationStatus } from '@/lib/types';

/* ------------------------------------------------------------------ headings */

export function ScreenHeader({
  number,
  title,
  lede,
  aside,
}: {
  number: string;
  title: string;
  lede: string;
  aside?: ReactNode;
}) {
  return (
    <header className="rule-b flex flex-wrap items-end justify-between gap-[var(--gap-wide)] pb-[var(--gap-wide)]">
      <div className="max-w-[46ch]">
        {/* The number is the Swiss device: it orients you in a five-screen app
            without a breadcrumb trail nobody reads. */}
        <p className="eyebrow mono mb-[var(--gap-tight)]">{number}</p>
        <h1 style={{ fontSize: 'var(--text-title)' }}>{title}</h1>
        <p className="mt-[var(--gap-tight)] text-[var(--text-small)] text-[var(--ink-soft)]">
          {lede}
        </p>
      </div>
      {aside ? <div className="flex items-center gap-[var(--gap-tight)]">{aside}</div> : null}
    </header>
  );
}

export function Section({
  label,
  hint,
  children,
  aside,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="mt-[var(--gap-section)] first:mt-[var(--gap-wide)]">
      <div className="mb-[var(--gap)] flex flex-wrap items-baseline justify-between gap-[var(--gap-tight)]">
        <div>
          <h2 className="eyebrow">{label}</h2>
          {hint ? (
            <p className="mt-[var(--gap-hair)] max-w-[62ch] text-[var(--text-small)] text-[var(--ink-soft)]">
              {hint}
            </p>
          ) : null}
        </div>
        {aside}
      </div>
      {children}
    </section>
  );
}

/* -------------------------------------------------------------------- status */

const STATUS_VAR: Record<ApplicationStatus, string> = {
  new: 'new',
  applied: 'applied',
  interview: 'interview',
  offer: 'offer',
  rejected: 'rejected',
  skipped: 'skipped',
};

export function StatusPill({ status }: { status: ApplicationStatus }) {
  const { t } = useTranslation();
  const name = STATUS_VAR[status];
  return (
    <span
      className="inline-flex items-center gap-[0.35rem] rounded-[var(--radius-round)] px-[0.5rem] py-[0.1rem] text-[var(--text-micro)] font-semibold uppercase tracking-[0.06em]"
      style={{
        background: `var(--status-${name}-soft)`,
        color: `var(--status-${name})`,
      }}
    >
      <span
        aria-hidden
        className="h-[0.4rem] w-[0.4rem] rounded-full"
        style={{ background: `var(--status-${name})` }}
      />
      {t(`status.${status}`)}
    </span>
  );
}

/* ------------------------------------------------------------------- inputs */

export function Labelled({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="eyebrow mb-[var(--gap-hair)] block">{label}</span>
      {children}
      {hint ? (
        <span className="mt-[var(--gap-hair)] block text-[var(--text-micro)] text-[var(--ink-faint)]">
          {hint}
        </span>
      ) : null}
    </label>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-[var(--gap-tight)] text-[var(--text-small)]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-[0.95rem] w-[0.95rem] accent-[var(--accent)]"
      />
      {label}
    </label>
  );
}

/**
 * A list of short strings the user builds up by typing.
 *
 * Enter commits, Backspace on an empty field removes the last one -- the
 * behaviour every chip input has, because anything else is a small betrayal of
 * muscle memory.
 */
export function ChipInput({
  values,
  onChange,
  placeholder,
  ariaLabel,
}: {
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  ariaLabel: string;
}) {
  const [draft, setDraft] = useState('');

  const commit = () => {
    const value = draft.trim();
    if (!value || values.includes(value)) {
      setDraft('');
      return;
    }
    onChange([...values, value]);
    setDraft('');
  };

  return (
    <div className="field flex flex-wrap items-center gap-[var(--gap-hair)] py-[0.3rem]">
      {values.map((value) => (
        <span
          key={value}
          className="inline-flex items-center gap-[0.3rem] rounded-[var(--radius-sharp)] bg-[var(--accent-soft)] px-[0.4rem] py-[0.1rem] text-[var(--text-small)]"
        >
          {value}
          <button
            type="button"
            className="text-[var(--ink-faint)] hover:text-[var(--bad)]"
            onClick={() => onChange(values.filter((item) => item !== value))}
            aria-label={`Remove ${value}`}
          >
            ×
          </button>
        </span>
      ))}
      <input
        aria-label={ariaLabel}
        className="min-w-[8rem] flex-1 bg-transparent outline-none"
        value={draft}
        placeholder={values.length ? '' : placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ',') {
            event.preventDefault();
            commit();
          } else if (event.key === 'Backspace' && !draft && values.length) {
            onChange(values.slice(0, -1));
          }
        }}
      />
    </div>
  );
}

/* -------------------------------------------------------------------- states */

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="panel-sunk px-[var(--gap-wide)] py-[var(--gap-section)] text-center text-[var(--text-small)] text-[var(--ink-faint)]">
      {children}
    </p>
  );
}

/**
 * The whole page, while a question about this machine is in flight.
 *
 * Deliberately almost nothing. The answer comes from a process on this
 * computer, so this is on screen for a few milliseconds, and a spinner that
 * flashes is worse than a word that does not.
 *
 * It is a whole screen rather than a line because of what it prevents: a screen
 * drawn from a half-answer has to guess, and the guess is visible. The front
 * page would offer a sign-in on an install with no accounts and then take it
 * away again -- for long enough to be clicked.
 */
export function Waiting() {
  const { t } = useTranslation();
  return (
    <div className="grid min-h-dvh place-items-center bg-[var(--ground-sunk)]">
      <p className="text-[var(--text-small)] text-[var(--ink-faint)]">{t('common.loading')}</p>
    </div>
  );
}

export function Loading() {
  const { t } = useTranslation();
  return (
    <p className="py-[var(--gap-wide)] text-[var(--text-small)] text-[var(--ink-faint)]">
      {t('common.loading')}
    </p>
  );
}

export function Problem({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="panel border-l-[3px] px-[var(--gap)] py-[var(--gap-tight)]"
      style={{ borderLeftColor: 'var(--bad)' }}
    >
      <p className="eyebrow" style={{ color: 'var(--bad)' }}>
        {t('error.title')}
      </p>
      <p className="mt-[var(--gap-hair)] text-[var(--text-small)]">{message}</p>
      {onRetry ? (
        <button type="button" className="btn btn-quiet mt-[var(--gap-tight)]" onClick={onRetry}>
          {t('common.retry')}
        </button>
      ) : null}
    </div>
  );
}

export function Note({
  tone = 'ok',
  children,
}: {
  tone?: 'ok' | 'warn' | 'bad';
  children: ReactNode;
}) {
  return (
    <p
      className="panel border-l-[3px] px-[var(--gap)] py-[var(--gap-tight)] text-[var(--text-small)]"
      style={{ borderLeftColor: `var(--${tone})` }}
    >
      {children}
    </p>
  );
}

/* -------------------------------------------------------------------- dialog */

export function Dialog({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { t } = useTranslation();

  useEffect(() => {
    ref.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-[oklch(20%_0.02_255_/_0.45)] p-[var(--gap-wide)]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="panel my-[4vh] w-full outline-none"
        style={{ maxWidth: wide ? '56rem' : '34rem' }}
      >
        <div className="rule-b flex items-center justify-between px-[var(--gap-wide)] py-[var(--gap)]">
          <h2 className="text-[var(--text-lead)] font-semibold">{title}</h2>
          <button
            type="button"
            className="btn btn-bare"
            onClick={onClose}
            aria-label={t('common.close')}
          >
            ×
          </button>
        </div>
        <div className="px-[var(--gap-wide)] py-[var(--gap-wide)]">{children}</div>
      </div>
    </div>
  );
}
