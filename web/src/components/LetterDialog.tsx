/**
 * The letter draft.
 *
 * The applicant's own details live in `localStorage` rather than on the server:
 * they are the same for every job, nobody wants to type them twice, and they
 * are exactly the sort of thing that should not end up in a file the user might
 * later share along with their spreadsheet.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { api } from '@/lib/api';
import type { JobRow } from '@/lib/types';
import { Dialog, Labelled, Problem } from '@/components/primitives';

const STORAGE_KEY = 'jobsheet.applicant';

interface Applicant {
  name: string;
  email: string;
  phone: string;
  pitch: string;
}

const BLANK: Applicant = { name: '', email: '', phone: '', pitch: '' };

function remembered(): Applicant {
  try {
    return { ...BLANK, ...(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Applicant) };
  } catch {
    return BLANK;
  }
}

export default function LetterDialog({ row, onClose }: { row: JobRow; onClose: () => void }) {
  const { t } = useTranslation();
  const [applicant, setApplicant] = useState<Applicant>(remembered);
  const [text, setText] = useState('');
  const [problem, setProblem] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(applicant));
  }, [applicant]);

  // Re-render on every keystroke would be one request per keystroke, so the
  // draft is rebuilt a beat after typing stops.
  useEffect(() => {
    const timer = setTimeout(() => {
      api
        .letter({
          dedup_key: row.dedup_key,
          applicant: {
            name: applicant.name || 'Your Name',
            email: applicant.email,
            phone: applicant.phone,
            pitch: applicant.pitch,
          },
        })
        .then((result) => {
          setText(result.text);
          setProblem('');
        })
        .catch((error: Error) => setProblem(error.message));
    }, 250);
    return () => clearTimeout(timer);
  }, [row.dedup_key, applicant]);

  return (
    <Dialog title={t('letter.title')} onClose={onClose} wide>
      <p className="mb-[var(--gap-wide)] max-w-[62ch] text-[var(--text-small)] text-[var(--ink-soft)]">
        {t('letter.lede')}
      </p>

      <div className="grid gap-[var(--gap-wide)] lg:grid-cols-[minmax(0,20rem)_1fr]">
        <div className="grid gap-[var(--gap)] self-start">
          <Labelled label={t('letter.yourName')}>
            <input
              className="field"
              value={applicant.name}
              onChange={(event) => setApplicant({ ...applicant, name: event.target.value })}
            />
          </Labelled>
          <Labelled label={t('letter.yourEmail')}>
            <input
              className="field"
              type="email"
              value={applicant.email}
              onChange={(event) => setApplicant({ ...applicant, email: event.target.value })}
            />
          </Labelled>
          <Labelled label={t('letter.yourPhone')}>
            <input
              className="field"
              value={applicant.phone}
              onChange={(event) => setApplicant({ ...applicant, phone: event.target.value })}
            />
          </Labelled>
          <Labelled label={t('letter.pitch')}>
            <textarea
              className="field min-h-[7rem]"
              placeholder={t('letter.pitchPlaceholder')}
              value={applicant.pitch}
              onChange={(event) => setApplicant({ ...applicant, pitch: event.target.value })}
            />
          </Labelled>
        </div>

        <div className="grid gap-[var(--gap-tight)]">
          {problem ? <Problem message={problem} /> : null}
          <textarea
            aria-label={t('letter.title')}
            className="field mono min-h-[24rem] leading-relaxed"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <div className="flex justify-end">
            <button
              type="button"
              className="btn btn-primary"
              onClick={async () => {
                await navigator.clipboard?.writeText(text);
                setCopied(true);
                setTimeout(() => setCopied(false), 1600);
              }}
            >
              {copied ? t('common.copied') : t('letter.copy')}
            </button>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
