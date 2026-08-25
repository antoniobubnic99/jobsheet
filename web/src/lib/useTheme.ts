/**
 * Light, dark, or whatever the system says.
 *
 * Three states rather than two, because "follow my computer" is a real
 * preference and forcing a choice between the other two ignores it. The
 * attribute goes on the root element; the CSS in `tokens.css` does the rest.
 */

import { useCallback, useEffect, useState } from 'react';

export type Theme = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'jobsheet.theme';
const ORDER: Theme[] = ['system', 'light', 'dark'];

function stored(): Theme {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === 'light' || value === 'dark' ? value : 'system';
}

function apply(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme);
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(stored);

  useEffect(() => {
    apply(theme);
    if (theme === 'system') localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const cycle = useCallback(() => {
    setTheme((current) => ORDER[(ORDER.indexOf(current) + 1) % ORDER.length] ?? 'system');
  }, []);

  return { theme, setTheme, cycle };
}
