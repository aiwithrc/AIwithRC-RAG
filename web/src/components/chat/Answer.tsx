import type { ReactNode } from 'react';

import { parseBlocks, plainText } from '../../lib/markdown';
import { cx } from '../ui';

/** Inline pieces: **bold**, *italic*, `code` and [n] citation chips. Unfinished markers mid-stream stay plain text. */
function inline(text: string, key: string, active: number | null, onCite?: (n: number) => void): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*|\[\d+\]|`[^`]+`|(?<![\w*])\*[^*\s][^*]*?\*(?![\w*]))/)
    .filter(Boolean)
    .map((part, i) => {
      const k = `${key}-${i}`;
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        return (
          <strong key={k} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        );
      }
      if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
        return (
          <code key={k} className="rounded bg-surface2 px-1 py-px font-mono text-[0.9em]">
            {part.slice(1, -1)}
          </code>
        );
      }
      if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
        return <em key={k}>{part.slice(1, -1)}</em>;
      }
      const m = part.match(/^\[(\d+)\]$/);
      if (m) {
        const n = Number(m[1]);
        const on = active === n;
        return onCite ? (
          <button
            key={k}
            type="button"
            onClick={() => onCite(n)}
            title="Show source"
            aria-label={`Show source ${n}`}
            className={cx(
              'mx-px inline-flex h-[19px] min-w-[19px] items-center justify-center rounded-[5px] border-none px-1 align-[2px] font-mono text-[11px] font-semibold',
              on ? 'bg-accent text-on-accent' : 'bg-accent-soft text-accent-text hover:bg-accent hover:text-on-accent',
            )}
          >
            {n}
          </button>
        ) : (
          <span
            key={k}
            className="mx-px inline-flex h-[19px] min-w-[19px] items-center justify-center rounded-[5px] bg-accent-soft px-1 align-[2px] font-mono text-[11px] font-semibold text-accent-text"
          >
            {n}
          </span>
        );
      }
      return <span key={k}>{part}</span>;
    });
}

/** Markdown for answers: headings, paragraphs, nested lists, tables, bold/italic/code and citation chips. */
export function AnswerText({
  text,
  active = null,
  onCite,
  className,
}: {
  text: string;
  active?: number | null;
  onCite?: (n: number) => void;
  className?: string;
}) {
  const blocks = parseBlocks(text);
  const ic = (t: string, k: string) => inline(t, k, active, onCite);
  return (
    <div className={cx('flex min-w-0 flex-col gap-3 text-pretty', className)}>
      {blocks.map((b, bi) => {
        if (b.kind === 'heading') {
          return (
            <div key={bi} role="heading" aria-level={Math.min(6, b.level + 1)} className={cx('font-semibold', bi > 0 && 'mt-1', b.level <= 2 ? 'text-[1.08em]' : 'text-[1em]')}>
              {ic(b.text, `${bi}`)}
            </div>
          );
        }
        if (b.kind === 'table') {
          return (
            <div key={bi} className="max-w-full overflow-x-auto rounded-[10px] border border-border">
              <table className="w-full border-collapse text-[0.92em]">
                <thead className="bg-surface2">
                  <tr>
                    {b.header.map((h, hi) => (
                      <th key={hi} className="min-w-[7.5rem] border-b border-border px-3 py-2 text-left font-semibold [overflow-wrap:anywhere]">
                        {ic(h, `${bi}-h${hi}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {b.rows.map((r, ri) => (
                    <tr key={ri} className="border-b border-border last:border-b-0">
                      {r.map((c, ci) => (
                        <td key={ci} className="min-w-[7.5rem] px-3 py-2 align-top [overflow-wrap:anywhere]">
                          {ic(c, `${bi}-${ri}-${ci}`)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (b.kind === 'list') {
          const Tag = b.ordered ? 'ol' : 'ul';
          return (
            <Tag key={bi} start={b.ordered && b.start !== 1 ? b.start : undefined} className={cx('m-0 flex flex-col gap-1.5 pl-5', b.ordered ? 'list-decimal' : 'list-disc')}>
              {b.items.map((it, li) => (
                <li key={li}>
                  {ic(it.text, `${bi}-${li}`)}
                  {it.children.length > 0 && (
                    <ul className="mt-1 flex list-[circle] flex-col gap-1 pl-5">
                      {it.children.map((c, ci) => (
                        <li key={ci}>{ic(c, `${bi}-${li}-${ci}`)}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </Tag>
          );
        }
        return (
          <p key={bi} className="m-0">
            {b.lines.map((l, li) => (
              <span key={li}>
                {li > 0 && <br />}
                {ic(l, `${bi}-${li}`)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

/** Plain text for the clipboard: no Markdown, citations as [n], sources listed underneath. */
export function answerForClipboard(text: string, sources: { n: number; filename: string; location: string }[]): string {
  const body = plainText(text);
  if (!sources.length) return body;
  return `${body}\n\nSources:\n${sources.map((s) => `[${s.n}] ${s.filename}${s.location ? ` · ${s.location}` : ''}`).join('\n')}`;
}
