/**
 * Select every source, only one country's, or none -- in one click instead of
 * fourteen. Shared by the wizard and the "edit search" screen, so a source
 * ticked in bulk gets the same starting parameters wherever it is ticked.
 */

import { useTranslation } from 'react-i18next';

import type { SourceManifest } from '@/lib/types';

export default function SourceBulkActions({
  sources,
  countries,
  chosenCount,
  onChoose,
}: {
  sources: SourceManifest[];
  countries: string[];
  chosenCount: number;
  onChoose: (wanted: SourceManifest[]) => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center gap-[var(--gap-tight)]">
      <button type="button" className="btn btn-quiet" onClick={() => onChoose(sources)}>
        {t('welcome.sources.all')}
      </button>
      {countries.map((country) => (
        <button
          key={country}
          type="button"
          className="btn btn-quiet"
          onClick={() => onChoose(sources.filter((source) => source.country === country))}
        >
          {t('welcome.sources.onlyCountry', { country })}
        </button>
      ))}
      <button type="button" className="btn btn-quiet" onClick={() => onChoose([])}>
        {t('welcome.sources.none')}
      </button>
      <span className="eyebrow ml-auto">{t('search.chosen', { count: chosenCount })}</span>
    </div>
  );
}
