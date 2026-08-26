/**
 * The door.
 *
 * Which form it shows is decided by the install, not by the visitor, because
 * the visitor cannot know which of the three situations they are in:
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
 */

import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';

import { api, ApiError } from '@/lib/api';
import { useAccount } from '@/lib/account';
import type { Account } from '@/lib/types';
import LanguagePicker from '@/components/LanguagePicker';
import { Loading, Problem } from '@/components/primitives';

type Mode = 'login' | 'register' | 'claim';

export default function SignInScreen() {
  const { t } = useTranslation();
  const { adopt } = useAccount();

  const status = useQuery({ queryKey: ['auth', 'status'], queryFn: api.auth.status });
  const [mode, setMode] = useState<Mode | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const claimable = status.data?.claimable ?? null;
  const accounts = status.data?.accounts ?? 0;

  // The install decides the opening form; a click can then override it, which
  // is why this only fires while `mode` is still unset.
  useEffect(() => {
    if (mode !== null || !status.data) return;
    setMode(claimable ? 'claim' : accounts === 0 ? 'register' : 'login');
    if (claimable) setUsername(claimable.username === 'local' ? '' : claimable.username);
  }, [mode, status.data, claimable, accounts]);

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

        {mode !== null ? (
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
          </form>
        ) : null}

        <p className="mt-[var(--gap)] max-w-[40ch] text-[var(--text-micro)] leading-snug text-[var(--ink-faint)]">
          {t('auth.localNote')}
        </p>

        <LanguagePicker className="mt-[var(--gap-wide)]" />
      </div>
    </div>
  );
}
