import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';

import './styles/global.css';
import './i18n';

import { AccountProvider } from './lib/account';
import Gate from './components/Gate';
import HomeScreen from './screens/HomeScreen';
import SearchScreen from './screens/SearchScreen';
import ResultsScreen from './screens/ResultsScreen';
import SheetDesigner from './screens/SheetDesigner';
import TrackerScreen from './screens/TrackerScreen';
import SettingsScreen from './screens/SettingsScreen';

// The server is on the same machine, so a request costs a millisecond and
// nothing is worth caching for long. Refetching on focus is what makes the
// results table agree with a workbook the user just edited in another window.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 2_000, retry: 1, refetchOnWindowFocus: true },
  },
});

const router = createBrowserRouter([
  {
    path: '/',
    // `Gate` decides between the door, the wizard and the app, and only the
    // last of the three renders an `Outlet` -- so these children exist for
    // every address but appear only once somebody is through both.
    element: <Gate />,
    children: [
      // The front page is the one button somebody presses every morning; the
      // form that made this search is a screen you visit when it needs
      // changing, so it has an address rather than the front page.
      { index: true, element: <HomeScreen /> },
      { path: 'search/edit', element: <SearchScreen /> },
      { path: 'results', element: <ResultsScreen /> },
      { path: 'designer', element: <SheetDesigner /> },
      { path: 'tracker', element: <TrackerScreen /> },
      { path: 'settings', element: <SettingsScreen /> },
      { path: '*', element: <HomeScreen /> },
    ],
  },
]);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AccountProvider>
        <RouterProvider router={router} />
      </AccountProvider>
    </QueryClientProvider>
  </StrictMode>,
);
