import type { ReactNode } from 'react';

import { cx } from '../ui';

/** Inline pieces: **bold** and [n] citation chips. Unfinished markers mid-stream stay plain text. */
function inline(text: string, key: string, active: number | null, onCite?: (n: number) => void): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*|\[\d+\])/)
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

/** Minimal Markdown for answers: paragraphs, bullet/numbered lists, bold, citation chips. */
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
  const blocks = text.split(/\n{2,}/).filter((b) => b.trim());
  return (
    <div className={cx('flex flex-col gap-3 text-pretty', className)}>
      {blocks.map((block, bi) => {
        const lines = block.split('\n').filter((l) => l.trim());
        const isList = lines.length > 0 && lines.every((l) => /^\s*(?:[-*•]|\d+[.)])\s+/.test(l));
        if (isList) {
          const ordered = /^\s*\d/.test(lines[0]);
          const Tag = ordered ? 'ol' : 'ul';
          return (
            <Tag key={bi} className={cx('m-0 flex flex-col gap-1.5 pl-5', ordered ? 'list-decimal' : 'list-disc')}>
              {lines.map((l, li) => (
                <li key={li}>{inline(l.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, ''), `${bi}-${li}`, active, onCite)}</li>
              ))}
            </Tag>
          );
        }
        return (
          <p key={bi} className="m-0">
            {lines.map((l, li) => (
              <span key={li}>
                {li > 0 && <br />}
                {inline(l.replace(/^#{1,6}\s+/, ''), `${bi}-${li}`, active, onCite)}
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
  const body = text.replace(/\*\*([^*]+)\*\*/g, '$1');
  if (!sources.length) return body;
  return `${body}\n\nSources:\n${sources.map((s) => `[${s.n}] ${s.filename}${s.location ? ` · ${s.location}` : ''}`).join('\n')}`;
}
