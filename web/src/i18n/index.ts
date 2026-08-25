/**
 * Two languages, both first-class.
 *
 * Croatian is here because the predecessor was Croatian and the four hardest
 * sources still are; English is here because the repository is public. Neither
 * is a translation of the other after the fact -- the strings were written in
 * both, which is why the Croatian ones read like Croatian rather than like
 * English with the words swapped.
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from './en.json';
import hr from './hr.json';

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'hr', label: 'Hrvatski' },
] as const;

export type LanguageCode = (typeof LANGUAGES)[number]['code'];

const STORAGE_KEY = 'jobsheet.language';

function initialLanguage(): LanguageCode {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === 'en' || saved === 'hr') return saved;
  // A Croatian browser gets Croatian without being asked. Anything else gets
  // English, which is the language the repository is written in.
  return navigator.language?.toLowerCase().startsWith('hr') ? 'hr' : 'en';
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hr: { translation: hr } },
  lng: initialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export function setLanguage(code: LanguageCode): void {
  localStorage.setItem(STORAGE_KEY, code);
  void i18n.changeLanguage(code);
  document.documentElement.lang = code;
}

document.documentElement.lang = i18n.language;

export default i18n;
