import { useEffect, useState } from 'react';

import type { Citation } from '../../api/client';
import { useIsMobile, useIsNarrow } from '../../hooks/useMediaQuery';
import { IconClose } from '../icons';
import { cx } from '../ui';

function typeLabel(filename: string) {
  const ext = filename.split('.').pop()?.toUpperCase() ?? '';
  return ext === 'MARKDOWN' ? 'MD' : ext.slice(0, 4);
}

/** Right-hand panel: one tab per citation, the matched passage with the supporting span highlighted. */
export function SourcePanel({
  citations,
  active,
  kbName,
  onSelect,
  onClose,
}: {
  citations: Citation[];
  active: number;
  kbName: string;
  onSelect: (n: number) => void;
  onClose: () => void;
}) {
  const mobile = useIsMobile();
  const narrow = useIsNarrow();
  const [copied, setCopied] = useState(false);
  const c = citations.find((x) => x.n === active) ?? citations[0];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  useEffect(() => setCopied(false), [active]);

  if (!c) return null;
  const pct = Math.round(c.score * 100);
  const openHref = `/api/documents/${c.document_id}/file${c.page ? `#page=${c.page}` : ''}`;

  return (
    <aside
      className={cx(
        'z-30 flex shrink-0 flex-col border-l border-border bg-surface',
        mobile ? 'absolute inset-0 w-full' : narrow ? 'absolute inset-y-0 right-0 w-[min(420px,100%)] shadow-card' : 'relative w-[400px]',
      )}
      aria-label="Source"
    >
      <div className="flex h-[52px] shrink-0 items-center gap-1.5 border-b border-border pl-5 pr-3">
        <div className="mr-2 text-[14px] font-semibold">Source</div>
        {citations.map((x) => (
          <button
            key={x.n}
            type="button"
            onClick={() => onSelect(x.n)}
            aria-label={`Source ${x.n}`}
            aria-pressed={x.n === c.n}
            className={cx(
              'h-[26px] w-[26px] rounded-[7px] border-none font-mono text-[12px] font-semibold',
              x.n === c.n ? 'bg-accent text-on-accent' : 'bg-surface2 text-muted hover:text-text',
            )}
          >
            {x.n}
          </button>
        ))}
        <div className="flex-1" />
        <button
          type="button"
          onClick={onClose}
          aria-label="Close source"
          className="flex h-8 w-8 items-center justify-center rounded-lg border-none bg-transparent text-muted hover:bg-surface2 hover:text-text"
        >
          <IconClose />
        </button>
      </div>
      <div className="flex flex-1 flex-col gap-5 overflow-auto p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[9px] bg-surface2 font-mono text-[10px] font-semibold text-muted">
            {typeLabel(c.filename)}
          </div>
          <div className="flex min-w-0 flex-col gap-[3px]">
            <div className="break-all font-mono text-[13px] font-medium">{c.filename}</div>
            {c.location && <div className="text-[12.5px] text-muted">{c.location}</div>}
          </div>
        </div>
        <div className="flex flex-col gap-[7px]">
          <div className="flex justify-between text-[12.5px]">
            <span className="text-muted">Relevance</span>
            <span className="font-mono font-medium">{c.score.toFixed(2)}</span>
          </div>
          <div className="h-[5px] overflow-hidden rounded-full bg-surface2">
            <div className={cx('h-full rounded-full', c.score > 0.75 ? 'bg-ok' : 'bg-warn')} style={{ width: `${pct}%` }} />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <div className="text-[12.5px] font-medium text-muted">Matched passage</div>
          <div className="whitespace-pre-line rounded-xl bg-surface2 px-[18px] py-4 text-[14.5px] leading-[1.75] text-muted text-pretty">
            {c.before}
            <mark className="rounded-[3px] bg-hl px-0.5 py-px text-text">{c.hit}</mark>
            {c.after}
          </div>
        </div>
        <div className="text-[12.5px] leading-[1.6] text-muted">
          Retrieved from {kbName}. Chunk {c.chunk} of {c.total}.
        </div>
        <div className="flex gap-2">
          <a
            href={openHref}
            target="_blank"
            rel="noreferrer"
            className="flex h-9 items-center rounded-[9px] border border-border bg-surface px-3.5 text-[13px] font-medium text-text hover:bg-surface2 hover:no-underline"
          >
            Open document
          </a>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard?.writeText(`${c.before}${c.hit}${c.after}`.replace(/^…|…$/g, '').trim()).then(() => setCopied(true));
            }}
            className="h-9 rounded-[9px] border border-border bg-surface px-3.5 text-[13px] font-medium text-text hover:bg-surface2"
          >
            {copied ? 'Copied' : 'Copy passage'}
          </button>
        </div>
      </div>
    </aside>
  );
}
