/** Small Markdown block parser for answers: headings, paragraphs, (one-level nested) lists and tables.
 * Line-based so it copes with half-streamed text; inline formatting is handled by the renderer. */

export type ListItem = { text: string; children: string[] };
export type Block =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'para'; lines: string[] }
  | { kind: 'list'; ordered: boolean; start: number; items: ListItem[] }
  | { kind: 'table'; header: string[]; rows: string[][] };

const ITEM = /^(\s*)(?:[-*•+]|(\d+)[.)])\s+(.*)$/;
const HEADING = /^\s*(#{1,6})\s+(.*?)\s*#*\s*$/;
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function cells(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
}

export function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const h = line.match(HEADING);
    if (h) {
      out.push({ kind: 'heading', level: h[1].length, text: h[2] });
      i++;
      continue;
    }
    if (line.trim().startsWith('|')) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++]);
      const sep = rows.findIndex((r) => TABLE_SEP.test(r));
      if (sep === 1) {
        out.push({ kind: 'table', header: cells(rows[0]), rows: rows.slice(2).map(cells) });
      } else {
        out.push({ kind: 'para', lines: rows });
      }
      continue;
    }
    const m = line.match(ITEM);
    if (m) {
      const ordered = !!m[2];
      const base = m[1].length;
      const items: ListItem[] = [];
      while (i < lines.length) {
        const l = lines[i];
        if (!l.trim()) {
          // A blank line ends the list unless the next line carries on with another item.
          const next = lines[i + 1];
          if (next && ITEM.test(next)) {
            i++;
            continue;
          }
          break;
        }
        const im = l.match(ITEM);
        if (im && im[1].length <= base + 1 && !!im[2] === ordered) {
          items.push({ text: im[3], children: [] });
        } else if (im && im[1].length > base + 1 && items.length) {
          items[items.length - 1].children.push(im[3]);
        } else if (!im && /^\s{2,}/.test(l) && items.length) {
          items[items.length - 1].text += ` ${l.trim()}`; // wrapped continuation line
        } else {
          break;
        }
        i++;
      }
      out.push({ kind: 'list', ordered, start: ordered ? Number(m[2]) : 1, items });
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !HEADING.test(lines[i]) && !ITEM.test(lines[i]) && !lines[i].trim().startsWith('|')) {
      para.push(lines[i++]);
    }
    out.push({ kind: 'para', lines: para });
  }
  return out;
}

/** Plain text without Markdown markup (for the clipboard). */
export function plainText(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/^\s*#{1,6}\s+/gm, '')
    .replace(/`([^`]+)`/g, '$1');
}
