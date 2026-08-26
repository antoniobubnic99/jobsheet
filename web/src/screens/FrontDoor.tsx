/**
 * Everything a signed-out browser sees: the front page, and the form behind it.
 *
 * The two are one screen conceptually -- you are outside -- so the choice
 * between them lives here rather than in `Gate`, which stays a decision about
 * *who* you are rather than about what you have clicked.
 *
 * The install decides which form the front page's first button opens, and it is
 * the same decision the form used to make for itself: a JobSheet holding a
 * search from before accounts offers to hand it over, anything else offers to
 * make an account. Deciding it here means the front page's button and the form
 * it opens can never disagree.
 *
 * `null` means the front page. There is no route for the form on purpose:
 * signing in is not a place you can be linked to or come back to with the back
 * button, it is a thing you are in the middle of.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { Waiting } from '@/components/primitives';
import LandingScreen from '@/screens/LandingScreen';
import SignInScreen, { type Mode } from '@/screens/SignInScreen';

export default function FrontDoor() {
  const status = useQuery({ queryKey: ['auth', 'status'], queryFn: api.auth.status });
  const [mode, setMode] = useState<Mode | null>(null);

  if (mode !== null) {
    return <SignInScreen initialMode={mode} onBack={() => setMode(null)} />;
  }

  // Waiting rather than guessing. Which actions the front page offers depends
  // on this answer, and an offer that appears and then withdraws is worse than
  // a moment of nothing -- it is long enough to be clicked.
  if (status.isPending) return <Waiting />;

  return (
    <LandingScreen
      status={status.data}
      onStart={() => setMode(status.data?.claimable ? 'claim' : 'register')}
      onSignIn={() => setMode('login')}
    />
  );
}
