import { describe, expect, it } from 'vitest';

import { parseBlocks, plainText } from './markdown';

describe('parseBlocks', () => {
  it('splits a paragraph from the list that follows it without a blank line', () => {
    const b = parseBlocks('The terms are:\n- **60 days** notice [1]\n- 30 days for breach [2]');
    expect(b.map((x) => x.kind)).toEqual(['para', 'list']);
    expect(b[1]).toMatchObject({ ordered: false, items: [{ text: '**60 days** notice [1]' }, { text: '30 days for breach [2]' }] });
  });

  it('parses headings, numbered lists with nested bullets and a start number', () => {
    const b = parseBlocks('## Steps\n\n3. First\n   - detail a\n   - detail b\n4. Second');
    expect(b[0]).toEqual({ kind: 'heading', level: 2, text: 'Steps' });
    expect(b[1]).toMatchObject({ kind: 'list', ordered: true, start: 3, items: [{ text: 'First', children: ['detail a', 'detail b'] }, { text: 'Second' }] });
  });

  it('keeps a list together across blank lines between items', () => {
    const b = parseBlocks('- one\n\n- two\n\nAfter.');
    expect(b.map((x) => x.kind)).toEqual(['list', 'para']);
    expect(b[0]).toMatchObject({ items: [{ text: 'one' }, { text: 'two' }] });
  });

  it('parses tables and leaves a half-streamed table as text', () => {
    const t = parseBlocks('| Item | Days |\n|---|---:|\n| Notice | 60 [1] |\n| Breach | 30 |');
    expect(t[0]).toEqual({ kind: 'table', header: ['Item', 'Days'], rows: [['Notice', '60 [1]'], ['Breach', '30']] });
    expect(parseBlocks('| Item | Da')[0].kind).toBe('para');
  });

  it('strips markup for the clipboard', () => {
    expect(plainText('## Title\n**Bold** and `code`')).toBe('Title\nBold and code');
  });
});
