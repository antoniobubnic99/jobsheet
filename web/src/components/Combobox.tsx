/**
 * A chip field that offers a list, without insisting on it.
 *
 * It exists because of the way a location field fails: it does not. Type
 * "Rijeka " with a trailing space, or "Rjeka", and the search runs perfectly and
 * finds nothing, and there is no message anywhere to say why. A list to pick
 * from removes a whole class of that, and it is the only fix that does -- a
 * validator could only tell somebody they were wrong after they had already
 * typed it.
 *
 * **Free text is always allowed.** JobSheet is not a Croatian application with
 * some foreign sources bolted on; RemoteOK, Remotive, Greenhouse, Lever and the
 * rest are global, and a field that refused "Ljubljana" or "remote" would be
 * worse than the blank one it replaced. The list suggests. It does not decide.
 *
 * The chip rules -- what a duplicate does, how many times Backspace has to be
 * pressed -- come from `useChips`, shared with the plain `ChipInput`, so the two
 * fields cannot drift apart.
 */

import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ChipHint, ChipList, useChips } from '@/components/primitives';

export interface Suggestion {
  /** What lands in the chip. */
  value: string;
  /** A word or two of context: the county a town is in, how often an employer appeared. */
  note?: string;
}

/** Long enough not to ask on every keystroke, short enough to feel like typing. */
const DEBOUNCE_MS = 140;

export default function Combobox({
  values,
  onChange,
  ariaLabel,
  placeholder,
  suggest,
  onPicked,
}: {
  values: string[];
  onChange: (next: string[]) => void;
  ariaLabel: string;
  placeholder?: string;
  /** Asked for suggestions as the user types. Returning nothing is not an error. */
  suggest: (query: string) => Promise<Suggestion[]>;
  /** Told which suggestion was taken, when the caller wants to act on it. */
  onPicked?: (suggestion: Suggestion) => void;
}) {
  const { t } = useTranslation();
  const chips = useChips(values, onChange);
  const [options, setOptions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);

  // Debounced, and every answer checked against the request that is current by
  // the time it lands: a slow reply for "ri" must not overwrite the list for
  // "rijek" that the user is already looking at.
  useEffect(() => {
    if (!open) return;
    let live = true;
    const timer = setTimeout(() => {
      void suggest(chips.draft).then((found) => {
        if (!live) return;
        setOptions(found.filter((one) => !values.includes(one.value)));
        setActive(-1);
      });
    }, DEBOUNCE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
    // `suggest` is rebuilt on every render by most callers, so it is deliberately
    // not a dependency -- including it would re-fetch on every keystroke twice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chips.draft, open, values]);

  const take = (suggestion: Suggestion) => {
    if (chips.add(suggestion.value)) onPicked?.(suggestion);
    setActive(-1);
    setOptions((current) => current.filter((one) => one.value !== suggestion.value));
  };

  const doomed = chips.armed ? chips.last : undefined;
  const showing = open && options.length > 0;

  return (
    <div className="relative" ref={box}>
      <div
        className="field flex flex-wrap items-center gap-[var(--gap-hair)] py-[0.3rem]"
        onMouseDown={chips.disarm}
      >
        <ChipList
          values={values}
          onChange={onChange}
          duplicate={chips.duplicate}
          doomed={doomed}
        />
        <input
          aria-label={ariaLabel}
          role="combobox"
          aria-expanded={showing}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          autoComplete="off"
          className="min-w-[8rem] flex-1 bg-transparent outline-none"
          value={chips.draft}
          placeholder={values.length ? '' : placeholder}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            chips.type(event.target.value);
            setOpen(true);
          }}
          onBlur={() => {
            // After the click, not before it: a mousedown on an option blurs the
            // input, and closing the list first would make the option unclickable.
            setTimeout(() => setOpen(false), 120);
            chips.blur();
          }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
              event.preventDefault();
              setOpen(true);
              if (!options.length) return;
              const step = event.key === 'ArrowDown' ? 1 : -1;
              setActive((current) => (current + step + options.length) % options.length);
              return;
            }
            if (event.key === 'Escape') {
              setOpen(false);
              setActive(-1);
              return;
            }
            // Enter on a highlighted option takes that one; Enter on nothing
            // commits whatever was typed, which is how free text gets in.
            if (event.key === 'Enter' && active >= 0 && options[active]) {
              event.preventDefault();
              take(options[active]);
              return;
            }
            chips.handleKey(event);
          }}
        />
        <ChipHint duplicate={chips.duplicate} doomed={doomed} />
      </div>

      {showing ? (
        <ul
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          className="panel absolute z-30 mt-[var(--gap-hair)] max-h-[14rem] w-full overflow-y-auto py-[var(--gap-hair)] shadow-lg"
        >
          {options.map((option, index) => (
            <li key={option.value} id={`${listId}-${index}`} role="option" aria-selected={index === active}>
              <button
                type="button"
                // `onMouseDown` rather than `onClick`: the click would land
                // after the blur that closes the list.
                onMouseDown={(event) => {
                  event.preventDefault();
                  take(option);
                }}
                onMouseEnter={() => setActive(index)}
                className="flex w-full items-baseline justify-between gap-[var(--gap-tight)] px-[var(--gap)] py-[0.2rem] text-left text-[var(--text-small)]"
                style={{ background: index === active ? 'var(--accent-soft)' : 'transparent' }}
              >
                <span>{option.value}</span>
                {option.note ? (
                  <span className="text-[var(--text-micro)] text-[var(--ink-faint)]">
                    {option.note}
                  </span>
                ) : null}
              </button>
            </li>
          ))}
          <li className="px-[var(--gap)] pt-[var(--gap-hair)] text-[var(--text-micro)] text-[var(--ink-faint)]">
            {t('common.orTypeYourOwn')}
          </li>
        </ul>
      ) : null}
    </div>
  );
}
