/**
 * Which of the three faces of JobSheet you are looking at.
 *
 * Signed out, you get the front door -- the page that says what this is, and
 * the sign-in form behind it. Signed in but never through the wizard, you get
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
import { Problem, Waiting } from '@/components/primitives';
import FrontDoor from '@/screens/FrontDoor';
import WelcomeScreen from '@/screens/WelcomeScreen';

export default function Gate() {
  const { t } = useTranslation();
  const { account, loading, unreachable, retry } = useAccount();

  if (loading) return <Waiting />;

  if (unreachable) {
    return (
      <div className="mx-auto max-w-[34rem] px-[var(--gap-wide)] py-[var(--gap-section)]">
        <Problem message={t('error.generic')} onRetry={retry} />
      </div>
    );
  }

  if (!account) return <FrontDoor />;
  if (!account.onboarded) return <WelcomeScreen />;
  return <Shell />;
}
