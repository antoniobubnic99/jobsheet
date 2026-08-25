/**
 * What the workbook will look like, drawn in the browser.
 *
 * Deliberately literal: grey column letters, a numbered gutter, the theme's
 * real header fill, the user's real widths. A schematic would be easier to
 * build and would fail at the one job this has -- letting someone decide
 * whether they like a design before they commit it to a file.
 *
 * Colours come from the server's theme record as `AARRGGBB`, which is what
 * openpyxl uses. Converting rather than keeping a second palette here is what
 * guarantees the preview and the file agree.
 */

import { useTranslation } from 'react-i18next';

import type { ColumnSpec, ExcelTheme, JobRow, SheetLayout } from '@/lib/types';
import { formatDate } from '@/lib/format';

/** `FF1F4E79` or `1F4E79` -> `#1F4E79`. */
export function cssColour(argb: string | undefined, fallback: string): string {
  if (!argb) return fallback;
  const hex = argb.length === 8 ? argb.slice(2) : argb;
  return /^[0-9a-f]{6}$/i.test(hex) ? `#${hex}` : fallback;
}

const COLUMN_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

function cellText(row: JobRow, column: ColumnSpec, locale: string): string {
  const posting = row.posting;
  switch (column.key) {
    case 'found_at':
      return formatDate(row.found_at, locale);
    case 'posted_at':
      return formatDate(posting.posted_at, locale);
    case 'deadline':
      return formatDate(posting.deadline, locale);
    case 'title':
      return posting.title;
    case 'company':
      return posting.company;
    case 'url':
      return row.link_text || posting.url;
    case 'location':
      return posting.location;
    case 'region':
      return posting.region;
    case 'workplace':
      return posting.workplace;
    case 'employment_type':
      return posting.employment_type;
    case 'education':
      return posting.education;
    case 'salary':
      return posting.salary;
    case 'source':
      return posting.source_id;
    case 'tags':
      return posting.tags.join(', ');
    case 'category':
      return row.category;
    case 'note':
      return row.note;
    case 'status':
      return row.status;
    default:
      return String(row.user_values[column.key] ?? '');
  }
}

export default function SheetPreview({
  layout,
  theme,
  rows,
  locale,
}: {
  layout: SheetLayout;
  theme: ExcelTheme | undefined;
  rows: JobRow[];
  locale: string;
}) {
  const { t } = useTranslation();

  const headerFill = cssColour(theme?.header_fill, '#1F4E79');
  const headerText = cssColour(theme?.header_text, '#FFFFFF');
  const zebraFill = cssColour(theme?.zebra_fill, '#F2F5F9');
  const border = cssColour(theme?.border, '#BFC7D1');
  const link = cssColour(theme?.link, '#1F4E79');

  const sample: (JobRow | null)[] = rows.length ? rows.slice(0, 6) : [null, null, null];

  return (
    <div className="panel scroll-x">
      <div className="rule-b flex items-center gap-[var(--gap-tight)] bg-[var(--ground-sunk)] px-[var(--gap)] py-[var(--gap-tight)]">
        <span
          className="rounded-t-[3px] px-[var(--gap-tight)] py-[0.1rem] text-[var(--text-micro)] font-semibold"
          style={{ background: headerFill, color: headerText }}
        >
          {layout.sheet_name}
        </span>
        <span className="text-[var(--text-micro)] text-[var(--ink-faint)]">
          {t('designer.previewHelp')}
        </span>
      </div>

      <div style={{ background: '#ffffff', color: '#16202c', minWidth: 'max-content' }}>
        <table
          className="tabular border-collapse text-[0.75rem]"
          style={{ borderColor: border }}
        >
          <thead>
            {/* The grey letter strip. It is what makes the thing read as a
                spreadsheet at a glance rather than as another web table. */}
            <tr>
              <th
                className="sticky left-0 z-10 w-[2rem] border px-1 text-center font-normal"
                style={{ background: '#e9edf2', borderColor: border, color: '#7a8593' }}
              />
              {layout.columns.map((column, index) => (
                <th
                  key={`letter-${column.key}`}
                  className="border px-1 text-center font-normal"
                  style={{ background: '#e9edf2', borderColor: border, color: '#7a8593' }}
                >
                  {COLUMN_LETTERS[index] ?? index + 1}
                </th>
              ))}
            </tr>
            <tr>
              <th
                className="sticky left-0 z-10 border px-1 text-center font-normal"
                style={{ background: '#e9edf2', borderColor: border, color: '#7a8593' }}
              >
                1
              </th>
              {layout.columns.map((column) => (
                <th
                  key={column.key}
                  className="whitespace-nowrap border px-2 py-1 text-left"
                  style={{
                    background: headerFill,
                    color: headerText,
                    borderColor: border,
                    minWidth: `${Math.max(4, column.width) * 0.52}rem`,
                  }}
                >
                  <span className="flex items-center gap-1">
                    {column.label}
                    {layout.autofilter ? <span aria-hidden>▾</span> : null}
                  </span>
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {sample.map((row, index) => (
              <tr
                key={index}
                style={{
                  background: layout.zebra && index % 2 === 1 ? zebraFill : '#ffffff',
                }}
              >
                <td
                  className="sticky left-0 z-10 border px-1 text-center"
                  style={{ background: '#e9edf2', borderColor: border, color: '#7a8593' }}
                >
                  {index + 2}
                </td>
                {layout.columns.map((column) => (
                  <td
                    key={column.key}
                    className="border px-2 py-[0.2rem] align-top"
                    style={{
                      borderColor: border,
                      whiteSpace: column.wrap ? 'normal' : 'nowrap',
                      maxWidth: column.wrap ? '18rem' : undefined,
                      color: column.kind === 'url' ? link : undefined,
                      textDecoration: column.kind === 'url' ? 'underline' : undefined,
                      // A column the app never writes to is shown empty here on
                      // purpose: the preview should not promise data it will
                      // not put there.
                      background:
                        column.user_owned && !row
                          ? 'repeating-linear-gradient(135deg,transparent,transparent 5px,#f4f6f9 5px,#f4f6f9 10px)'
                          : undefined,
                    }}
                  >
                    {column.kind === 'checkbox' ? (
                      <span aria-hidden>☐</span>
                    ) : row ? (
                      <span className="line-clamp-2 block overflow-hidden">
                        {cellText(row, column, locale)}
                      </span>
                    ) : (
                      ''
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
