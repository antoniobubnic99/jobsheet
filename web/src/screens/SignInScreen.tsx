/**
 * The form behind the front page.
 *
 * Which form it opens on is decided by the install, not by the visitor, because
 * the visitor cannot know which of the three situations they are in. `FrontDoor`
 * makes that call and hands it down as `initialMode`; from then on the switches
 * at the bottom of the form belong to the visitor:
 *
 * * **Nobody here yet.** One form, "make your account". Offering a sign-in box
 *   to somebody who has nothing to sign into is a small cruelty.
 * * **Data waiting to be claimed.** This install was used before it had
 *   accounts. The waiting search is offered first, by name, because the person
 *   at the keyboard is almost certainly the person who made it -- and if they
 *   are not, "start fresh instead" is one click away.
 * * **Accounts exist.** Sign in, with a quieter way to add another.
 *
 * Errors are translated by code where the interface knows one and shown in the
 * server's own words where it does not, which means a new failure the backend
 * invents still reaches the user as a sentence rather than a status number.
 *
 * `onBack` returns to the front page. It is a button rather than history,
 * because there is no history to go back to -- the front page and this form are
 * the same address.
 */

import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';

import { api, ApiError } from '@/lib/api';
import { useAccount } from '@/lib/account';
import type { Account } from '@/lib/types';
import LanguagePicker from '@/components/LanguagePicker';
import { Loading, Problem } from '@/components/primitives';

export type Mode = 'login' | 'register' | 'claim';

export default function SignInScreen({
  initialMode,
  onBack,
}: {
  initialMode: Mode;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const { adopt } = useAccount();

  // Already answered for the front page, so this reads the cache rather than
  // asking again.
  const status = useQuery({ queryKey: ['auth', 'status'], queryFn: api.auth.status });
  const [mode, setMode] = useState<Mode>(initialMode);
  const claimable = status.data?.claimable ?? null;
  const accounts = status.data?.accounts ?? 0;

  // The waiting account's own name is the best guess at what its owner wants to
  // be called -- except for `local`, which is the name the migration invented
  // for a JobSheet that had no accounts, and which nobody chose.
  const [username, setUsername] = useState(() =>
    initialMode === 'claim' && claimable && claimable.username !== 'local'
      ? claimable.username
      : '',
  );
  const [password, setPassword] = useState('');

  const submit = useMutation<Account, Error, void>({
    mutationFn: () => {
      const name = username.trim();
      if (mode === 'register') return api.auth.register(name, password);
      if (mode === 'claim') return api.auth.claim(name, password);
      return api.auth.login(name, password);
    },
    onSuccess: (account) => {
      setPassword('');
      adopt(account);
    },
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) return;
    submit.mutate();
  };

  // Whether the row of switches at the bottom has anything to offer. Without
  // this the rule above it is drawn on a fresh install, where every switch is
  // hidden -- a line under nothing, which reads as a section that failed to
  // load rather than as one that does not apply.
  const canSwitch =
    mode === 'login' || mode === 'claim' || (mode === 'register' && accounts > 0) || !!claimable;

  const failure = submit.error;
  const message =
    failure instanceof ApiError
      ? // A translated sentence when we know the code, the server's own when we
        // do not. `defaultValue` is what makes the second half true.
        t(`auth.errors.${failure.code}`, { defaultValue: failure.message })
      : failure
        ? t('error.generic')
        : '';

  return (
    <div className="min-h-dvh bg-[var(--ground-sunk)] px-[var(--gap-wide)] py-[var(--gap-section)]">
      <div className="mx-auto w-full max-w-[26rem]">
        <button type="button" className="btn btn-bare mb-[var(--gap)] px-0" onClick={onBack}>
          <span aria-hidden>&larr;</span> {t('auth.back')}
        </button>

        <header className="mb-[var(--gap-wide)]">
          <p className="eyebrow mono mb-[var(--gap-tight)]">00</p>
          <p className="text-[2rem] font-bold leading-none tracking-[-0.035em]">
            Job<span className="text-[var(--accent)]">Sheet</span>
          </p>
          <p className="mt-[var(--gap-tight)] max-w-[34ch] text-[var(--text-small)] leading-snug text-[var(--ink-soft)]">
            {t('app.tagline')}
          </p>
        </header>

        {status.isPending ? <Loading /> : null}
        {status.error ? (
          <Problem message={t('error.generic')} onRetry={() => void status.refetch()} />
        ) : null}

        <form onSubmit={onSubmit} className="panel p-[var(--gap-wide)]">
          <h1 className="text-[var(--text-lead)] font-semibold">{t(`auth.${mode}.title`)}</h1>
          <p className="mt-[var(--gap-hair)] text-[var(--text-small)] text-[var(--ink-soft)]">
            {mode === 'claim'
              ? t('auth.claim.lede', { name: claimable?.username ?? '' })
              : t(`auth.${mode}.lede`)}
          </p>

          <div className="mt-[var(--gap-wide)] grid gap-[var(--gap)]">
            <label className="block">
              <span className="eyebrow mb-[var(--gap-hair)] block">{t('auth.username')}</span>
              <input
                className="field"
                value={username}
                autoFocus
                autoComplete="username"
                spellCheck={false}
                onChange={(event) => setUsername(event.target.value)}
              />
              {mode !== 'login' ? (
                <span className="mt-[var(--gap-hair)] block text-[var(--text-micro)] text-[var(--ink-faint)]">
                  {t('auth.usernameHint')}
                </span>
              ) : null}
            </label>

            <label className="block">
              <span className="eyebrow mb-[var(--gap-hair)] block">{t('auth.password')}</span>
              <input
                className="field"
                type="password"
                value={password}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                onChange={(event) => setPassword(event.target.value)}
              />
              {mode !== 'login' ? (
                <span className="mt-[var(--gap-hair)] block text-[var(--text-micro)] text-[var(--ink-faint)]">
                  {t('auth.passwordHint')}
                </span>
              ) : null}
            </label>
          </div>

          {message ? (
            <p
              role="alert"
              className="mt-[var(--gap)] border-l-[3px] pl-[var(--gap-tight)] text-[var(--text-small)]"
              style={{ borderLeftColor: 'var(--bad)' }}
            >
              {message}
            </p>
          ) : null}

          <button
            type="submit"
            className="btn btn-primary mt-[var(--gap-wide)] w-full justify-center"
            disabled={submit.isPending || !username.trim() || !password}
          >
            {submit.isPending ? t('auth.working') : t(`auth.${mode}.action`)}
          </button>

          {canSwitch ? (
            <div className="rule-t mt-[var(--gap-wide)] pt-[var(--gap)] text-[var(--text-small)]">
              {mode === 'login' ? (
                <button
                  type="button"
                  className="btn btn-bare px-0"
                  onClick={() => {
                    setMode('register');
                    submit.reset();
                  }}
                >
                  {t('auth.switchToRegister')}
                </button>
              ) : null}

              {mode === 'register' && accounts > 0 ? (
                <button
                  type="button"
                  className="btn btn-bare px-0"
                  onClick={() => {
                    setMode('login');
                    submit.reset();
                  }}
                >
                  {t('auth.switchToLogin')}
                </button>
              ) : null}

              {mode === 'claim' ? (
                <button
                  type="button"
                  className="btn btn-bare px-0"
                  onClick={() => {
                    setMode('register');
                    setUsername('');
                    submit.reset();
                  }}
                >
                  {t('auth.switchToFresh')}
                </button>
              ) : null}

              {mode !== 'claim' && claimable ? (
                <button
                  type="button"
                  className="btn btn-bare px-0"
                  onClick={() => {
                    setMode('claim');
                    submit.reset();
                  }}
                >
                  {t('auth.switchToClaim')}
                </button>
              ) : null}
            </div>
          ) : null}
        </form>

        <p className="mt-[var(--gap)] max-w-[40ch] text-[var(--text-micro)] leading-snug text-[var(--ink-faint)]">
          {t('auth.localNote')}
        </p>

        <LanguagePicker className="mt-[var(--gap-wide)]" />
      </div>
    </div>
  );
}
