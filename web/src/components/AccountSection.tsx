/**
 * The account block on the settings screen: who you are, and a new password.
 *
 * Changing a password signs every window out, this one included, and the
 * confirmation says so before the screen goes back to the sign-in form. A
 * change that silently dropped you at the door would read as a failure -- as
 * though the new password had not been accepted -- which is the opposite of
 * what just happened.
 */

import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';

import { api, ApiError } from '@/lib/api';
import { useAccount } from '@/lib/account';
import { Section } from '@/components/primitives';

export default function AccountSection() {
  const { t } = useTranslation();
  const { account, signOut } = useAccount();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [done, setDone] = useState(false);

  const change = useMutation({
    mutationFn: () => api.auth.changePassword(current, next),
    onSuccess: () => {
      setCurrent('');
      setNext('');
      setDone(true);
    },
  });

  const failure = change.error;
  const message =
    failure instanceof ApiError
      ? t(`auth.errors.${failure.code}`, { defaultValue: failure.message })
      : failure
        ? t('error.generic')
        : '';

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!current || !next) return;
    change.mutate();
  };

  return (
    <Section label={t('auth.account')} hint={t('auth.accountHint')}>
      <div className="panel p-[var(--gap-wide)]">
        <div className="flex flex-wrap items-baseline justify-between gap-[var(--gap)]">
          <p className="text-[var(--text-lead)] font-semibold">{account?.username}</p>
          <button type="button" className="btn btn-quiet" onClick={() => void signOut()}>
            {t('auth.signOut')}
          </button>
        </div>

        <form onSubmit={onSubmit} className="rule-t mt-[var(--gap)] pt-[var(--gap)]">
          <h3 className="eyebrow mb-[var(--gap-tight)]">{t('auth.changePassword')}</h3>
          <div className="grid gap-[var(--gap-tight)] sm:grid-cols-2">
            <label className="block">
              <span className="eyebrow mb-[var(--gap-hair)] block">
                {t('auth.currentPassword')}
              </span>
              <input
                className="field"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
              />
            </label>
            <label className="block">
              <span className="eyebrow mb-[var(--gap-hair)] block">{t('auth.newPassword')}</span>
              <input
                className="field"
                type="password"
                autoComplete="new-password"
                value={next}
                onChange={(event) => setNext(event.target.value)}
              />
            </label>
          </div>

          {message ? (
            <p
              role="alert"
              className="mt-[var(--gap-tight)] border-l-[3px] pl-[var(--gap-tight)] text-[var(--text-small)]"
              style={{ borderLeftColor: 'var(--bad)' }}
            >
              {message}
            </p>
          ) : null}

          {done ? (
            <p
              className="mt-[var(--gap-tight)] border-l-[3px] pl-[var(--gap-tight)] text-[var(--text-small)]"
              style={{ borderLeftColor: 'var(--ok)' }}
            >
              {t('auth.passwordChanged')}
            </p>
          ) : null}

          <button
            type="submit"
            className="btn btn-quiet mt-[var(--gap)]"
            disabled={change.isPending || !current || !next}
          >
            {change.isPending ? t('auth.working') : t('auth.changePassword')}
          </button>
        </form>
      </div>
    </Section>
  );
}
