/**
 * The column list.
 *
 * Reordering by drag is hard to drive from a test and easy to see by eye;
 * everything else about this component is logic that would break silently, so
 * that is what is tested here.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import '@/i18n';
import ColumnList from './ColumnList';
import type { ColumnSpec, LayoutVocabulary } from '@/lib/types';

const VOCABULARY: LayoutVocabulary = {
  kinds: [
    { value: 'text', label: 'Text' },
    { value: 'date', label: 'Date' },
    { value: 'checkbox', label: 'Checkbox' },
  ],
  source_keys: ['title', 'company', 'url'],
  themes: [],
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

describe('ColumnList', () => {
  it('shows one row per column', () => {
    render(
      <ColumnList
        columns={[column(), column({ key: 'company', label: 'Company' })]}
        vocabulary={VOCABULARY}
        onChange={() => {}}
      />,
    );

    expect(screen.getByDisplayValue('Position')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Company')).toBeInTheDocument();
  });

  it('reports a renamed heading', async () => {
    const onChange = vi.fn();
    render(
      <ColumnList columns={[column()]} vocabulary={VOCABULARY} onChange={onChange} />,
    );

    await userEvent.type(screen.getByDisplayValue('Position'), '!');

    expect(onChange).toHaveBeenCalled();
    const [next] = onChange.mock.calls.at(-1) as [ColumnSpec[]];
    expect(next[0]?.label).toBe('Position!');
  });

  it('removes the column that was asked for, not another one', async () => {
    const onChange = vi.fn();
    render(
      <ColumnList
        columns={[column(), column({ key: 'company', label: 'Company' })]}
        vocabulary={VOCABULARY}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByLabelText('Remove Company'));

    const [next] = onChange.mock.calls.at(-1) as [ColumnSpec[]];
    expect(next.map((item) => item.key)).toEqual(['title']);
  });

  it('refuses to remove the last column', () => {
    render(
      <ColumnList columns={[column()]} vocabulary={VOCABULARY} onChange={() => {}} />,
    );

    expect(screen.getByLabelText('Remove Position')).toBeDisabled();
  });

  it('marks a column the app must never write to', () => {
    render(
      <ColumnList
        columns={[column({ key: 'my_notes', label: 'My notes', user_owned: true })]}
        vocabulary={VOCABULARY}
        onChange={() => {}}
      />,
    );

    expect(screen.getByText('Yours')).toBeInTheDocument();
  });

  it('offers the keys the app knows how to fill', () => {
    const { container } = render(
      <ColumnList columns={[column()]} vocabulary={VOCABULARY} onChange={() => {}} />,
    );

    const options = [...container.querySelectorAll('#jobsheet-source-keys option')];
    expect(options.map((option) => option.getAttribute('value'))).toEqual([
      'title',
      'company',
      'url',
    ]);
  });

  it('offers only the column kinds the server declared', () => {
    render(
      <ColumnList columns={[column()]} vocabulary={VOCABULARY} onChange={() => {}} />,
    );

    const select = screen.getByLabelText(/Type/i) as HTMLSelectElement;
    expect([...select.options].map((option) => option.value)).toEqual([
      'text',
      'date',
      'checkbox',
    ]);
  });

  it('every row can be reordered from the keyboard', () => {
    /** A designer that only works by dragging is closed to keyboard users. */
    render(
      <ColumnList
        columns={[column(), column({ key: 'company', label: 'Company' })]}
        vocabulary={VOCABULARY}
        onChange={() => {}}
      />,
    );

    for (const label of ['Position', 'Company']) {
      expect(screen.getByLabelText(`Reorder ${label}`)).toBeInTheDocument();
    }
  });
});
