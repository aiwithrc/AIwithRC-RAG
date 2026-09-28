import { useEffect, useRef, useState, type ReactNode } from 'react';

import { useIsMobile } from '../hooks/useMediaQuery';
import { IconCheck, IconChevronDown } from './icons';
import { cx } from './ui';

/** Header picker button + popover menu, as in the prototype's KB and model pickers. */
export function Dropdown({
  label,
  leading,
  heading,
  width = 300,
  footer,
  children,
}: {
  label: ReactNode;
  leading?: ReactNode;
  heading: string;
  width?: number;
  footer?: (close: () => void) => ReactNode;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const mobile = useIsMobile();
  const ref = useRef<HTMLDivElement>(null);
  const close = () => setOpen(false);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex h-[34px] items-center gap-2 rounded-[9px] border border-border bg-surface px-2.5 text-[13px] font-medium text-text hover:bg-surface2"
        style={{ maxWidth: mobile ? 118 : 220 }}
      >
        {leading}
        <span className="truncate">{label}</span>
        <IconChevronDown className="shrink-0 text-muted" />
      </button>
      {open && (
        <div
          className="absolute right-0 top-10 z-[25] max-w-[88vw] rounded-xl border border-border bg-surface p-1.5 shadow-card"
          style={{ width }}
          role="menu"
        >
          <div className="px-2.5 pb-1.5 pt-2 text-[12px] font-medium text-muted">{heading}</div>
          {children(close)}
          {footer && <div className="mt-1.5 border-t border-border pt-1.5">{footer(close)}</div>}
        </div>
      )}
    </div>
  );
}

export function DropdownItem({
  onSelect,
  selected,
  children,
  trailing,
}: {
  onSelect: () => void;
  selected?: boolean;
  children: ReactNode;
  trailing?: ReactNode;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onSelect}
      className="flex w-full items-center gap-2.5 rounded-lg border-none bg-transparent px-2.5 py-[9px] text-left text-text hover:bg-surface2"
    >
      <div className="min-w-0 flex-1">{children}</div>
      {trailing}
      <span className={cx('w-4 text-accent-text', selected ? 'opacity-100' : 'opacity-0')}>
        <IconCheck />
      </span>
    </button>
  );
}
