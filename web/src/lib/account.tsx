/**
 * Who is signed in, for the whole interface.
 *
 * There is no token to hold here and nothing to put in `localStorage`. The
 * session lives in an HttpOnly cookie the browser attaches by itself, which
 * means this file cannot read it -- and neither can any other script on the
 * page. What it can do is *ask*: `/api/auth/me` answers with an account or a
 * 401, and that single answer decides which of the three faces of the app the
 * viewer sees.
 *
 * A 401 is therefore not an error. It is the signed-out state, and treating it
 * as a failure would put a red box on the sign-in screen every time somebody
 * opened JobSheet for the first time. Only an unreachable server is an error.
 *
 * The cache is emptied on every change of account, in both directions. Without
 * that, signing out and signing in as somebody else would leave React Query
 * holding the last person's job list and hand it straight to the next one --
 * the same silent failure the database guards against, one layer up.
 */

import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { api, ApiError } from '@/lib/api';
import type { Account } from '@/lib/types';

interface AccountState {
  /** `null` means signed out, which is an ordinary state, not a failure. */
  account: Account | null;
  loading: boolean;
  /** Set only when JobSheet itself could not be reached. */
  unreachable: string;
  retry: () => void;
  /** Take up a freshly signed-in account and drop whatever the last one cached. */
  adopt: (account: Account) => void;
  signOut: () => Promise<void>;
}

const AccountContext = createContext<AccountState | null>(null);

export const ACCOUNT_KEY = ['auth', 'me'] as const;

async function whoIsHere(): Promise<Account | null> {
  try {
    return await api.auth.me();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export function AccountProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const me = useQuery({
    queryKey: ACCOUNT_KEY,
    queryFn: whoIsHere,
    retry: false,
    // The server is on this machine. Refetching on focus is how a second tab
    // notices that the first one signed out.
    refetchOnWindowFocus: true,
    staleTime: 5_000,
  });

  /**
   * Throw away every cached answer that belonged to the last account.
   *
   * Everything *except* the account query itself, which is the subtlety worth
   * stating: `clear()` would drop that one too, and the observer watching it
   * would immediately refetch -- so the account we are about to write would be
   * overwritten a moment later by whatever that request happened to return.
   * The wizard is where it shows: finish, and the app flashes back to the
   * wizard because the in-flight `me` still says the account is not onboarded.
   */
  const forgetTheLastAccount = useCallback(() => {
    queryClient.removeQueries({
      predicate: (query) => !(query.queryKey[0] === 'auth' && query.queryKey[1] === 'me'),
    });
  }, [queryClient]);

  const adopt = useCallback(
    (account: Account) => {
      forgetTheLastAccount();
      queryClient.setQueryData(ACCOUNT_KEY, account);
    },
    [queryClient, forgetTheLastAccount],
  );

  const signOut = useCallback(async () => {
    try {
      await api.auth.logout();
    } finally {
      // Even if the call failed, this browser is done with that account. The
      // cookie is gone or the server refused; either way, show the door.
      forgetTheLastAccount();
      queryClient.setQueryData(ACCOUNT_KEY, null);
    }
  }, [queryClient, forgetTheLastAccount]);

  const value = useMemo<AccountState>(
    () => ({
      account: me.data ?? null,
      loading: me.isPending,
      unreachable: me.error ? String((me.error as Error).message ?? me.error) : '',
      retry: () => void me.refetch(),
      adopt,
      signOut,
    }),
    [me, adopt, signOut],
  );

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

export function useAccount(): AccountState {
  const value = useContext(AccountContext);
  if (value === null) {
    throw new Error('useAccount must be used inside an AccountProvider');
  }
  return value;
}
