/**
 * The live preview.
 *
 * This is what a user looks at while deciding whether they like a design, so
 * the thing worth testing is that it tells the truth: the user's headings, the
 * user's order, the theme's real colours, and no promise of data in a column
 * the app will never fill.
 */

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import '@/i18n';
import SheetPreview, { cssColour } from './SheetPreview';
import type { ColumnSpec, ExcelTheme, JobRow, SheetLayout } from '@/lib/types';

const THEME: ExcelTheme = {
  value: 'navy',
  default: true,
  header_fill: 'FF1F4E79',
  header_text: 'FFFFFFFF',
  zebra_fill: 'FFF2F5F9',
  border: 'FFBFC7D1',
  link: 'FF1F4E79',
};

function column(over: Partial<ColumnSpec> = {}): ColumnSpec {
  return {
    key: 'title',
    label: 'Position',
    kind: 'text',
    width: 30,
    wrap: false,
    user_owned: false,
    ...over,
  };
}

function layout(over: Partial<SheetLayout> = {}): SheetLayout {
  return {
    sheet_name: 'Jobs',
    columns: [column(), column({ key: 'company', label: 'Company' })],
    theme: 'navy',
    freeze_header: true,
    autofilter: true,
    zebra: false,
    rules: [],
    ...over,
  };
}

const ROW: JobRow = {
  dedup_key: 'example.test/j/1',
  posting: {
    source_id: 'rss',
    title: 'GIS Engineer',
    url: 'https://example.test/j/1',
    company: 'Kartograf d.o.o.',
    location: 'Rijeka',
    region: '',
    workplace: 'hybrid',
    description: '',
    employment_type: '',
    education: '',
    salary: '',
    posted_at: '2026-08-01',
    deadline: '2026-09-01',
    tags: ['gis'],
  },
  found_at: '2026-08-24',
  category: 'GIS',
  note: 'matched "gis" in the title',
  status: 'new',
  user_values: {},
  link_text: '',
};

describe('cssColour', () => {
  it('drops the alpha channel openpyxl carries', () => {
    expect(cssColour('FF1F4E79', '#000')).toBe('#1F4E79');
  });

  it('accepts a plain six-digit colour', () => {
    expect(cssColour('1F4E79', '#000')).toBe('#1F4E79');
  });

  it('falls back rather than emitting nonsense', () => {
    expect(cssColour(undefined, '#123456')).toBe('#123456');
    expect(cssColour('not a colour', '#123456')).toBe('#123456');
  });
});

describe('SheetPreview', () => {
  it('shows the headings the user typed', () => {
    render(<SheetPreview layout={layout()} theme={THEME} rows={[ROW]} locale="en" />);

    expect(screen.getByText('Position')).toBeInTheDocument();
    expect(screen.getByText('Company')).toBeInTheDocument();
  });

  it('shows them in the order the user arranged', () => {
    render(
      <SheetPreview
        layout={layout({ columns: [column({ key: 'company', label: 'Company' }), column()] })}
        theme={THEME}
        rows={[ROW]}
        locale="en"
      />,
    );

    const headings = screen.getAllByRole('columnheader').map((cell) => cell.textContent);
    expect(headings.indexOf('Company▾')).toBeLessThan(headings.indexOf('Position▾'));
  });

  it('fills the sample rows from real jobs', () => {
    render(<SheetPreview layout={layout()} theme={THEME} rows={[ROW]} locale="en" />);

    expect(screen.getByText('GIS Engineer')).toBeInTheDocument();
    expect(screen.getByText('Kartograf d.o.o.')).toBeInTheDocument();
  });

  it('paints the header in the theme, not in a colour of its own', () => {
    const { container } = render(
      <SheetPreview layout={layout()} theme={THEME} rows={[ROW]} locale="en" />,
    );

    const header = container.querySelector('thead tr:nth-child(2) th:nth-child(2)');
    expect(header).toHaveStyle({ background: '#1F4E79' });
  });

  it('draws a checkbox column as a checkbox', () => {
    render(
      <SheetPreview
        layout={layout({ columns: [column({ key: 'applied', label: 'Applied', kind: 'checkbox' })] })}
        theme={THEME}
        rows={[ROW]}
        locale="en"
      />,
    );

    expect(screen.getAllByText('☐').length).toBeGreaterThan(0);
  });

  it('shows the tab name so the user knows what the sheet is called', () => {
    render(
      <SheetPreview layout={layout({ sheet_name: 'My hunt' })} theme={THEME} rows={[]} locale="en" />,
    );

    expect(screen.getByText('My hunt')).toBeInTheDocument();
  });

  it('shows the spreadsheet letter strip, so it reads as a spreadsheet', () => {
    const { container } = render(
      <SheetPreview layout={layout()} theme={THEME} rows={[ROW]} locale="en" />,
    );

    const letters = container.querySelector('thead tr:first-child');
    expect(within(letters as HTMLElement).getByText('A')).toBeInTheDocument();
    expect(within(letters as HTMLElement).getByText('B')).toBeInTheDocument();
  });

  it('still draws a table when there is nothing collected yet', () => {
    render(<SheetPreview layout={layout()} theme={THEME} rows={[]} locale="en" />);
    expect(screen.getByText('Position')).toBeInTheDocument();
  });
});
