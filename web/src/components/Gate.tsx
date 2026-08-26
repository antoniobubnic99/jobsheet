/**
 * Which of the three faces of JobSheet you are looking at.
 *
 * Signed out, you get the door. Signed in but never through the wizard, you get
 * the wizard. Otherwise you get the app. That is the whole decision, and it is
 * made in one place so no screen has to defend itself.
 *
 * There is no redirecting. A guard that navigates would put `/login` in the
 * history and let the back button walk into a screen that is not there any
 * more; a guard that simply renders something else leaves the address alone, so
 * `/tracker` is still `/tracker` once you have signed in and the app appears
 * exactly where you were headed.
 */

import { useTranslation } from 'react-i18next';

import { useAccount } from '@/lib/account';
import Shell from '@/components/Shell';
import { Problem } from '@/components/primitives';
import SignInScreen from '@/screens/SignInScreen';
import WelcomeScreen from '@/screens/WelcomeScreen';

export default function Gate() {
  const { t } = useTranslation();
  const { account, loading, unreachable, retry } = useAccount();

  if (loading) {
    // Deliberately almost nothing. The answer comes from a process on this
    // machine, so this is on screen for a few milliseconds, and a spinner that
    // flashes is worse than a word that does not.
    return (
      <div className="grid min-h-dvh place-items-center bg-[var(--ground-sunk)]">
        <p className="text-[var(--text-small)] text-[var(--ink-faint)]">{t('common.loading')}</p>
      </div>
    );
  }

  if (unreachable) {
    return (
      <div className="mx-auto max-w-[34rem] px-[var(--gap-wide)] py-[var(--gap-section)]">
        <Problem message={t('error.generic')} onRetry={retry} />
      </div>
    );
  }

  if (!account) return <SignInScreen />;
  if (!account.onboarded) return <WelcomeScreen />;
  return <Shell />;
}
