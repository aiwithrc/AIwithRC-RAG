import { useEffect, type ReactNode } from 'react';

import { Button } from './ui';

export function Modal({
  open,
  onClose,
  width = 460,
  children,
  labelledBy,
}: {
  open: boolean;
  onClose: () => void;
  width?: number;
  children: ReactNode;
  labelledBy?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-overlay p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        onClick={(e) => e.stopPropagation()}
        className="flex w-full flex-col gap-[18px] rounded-2xl border border-border bg-surface p-[22px] shadow-card"
        style={{ maxWidth: width }}
      >
        {children}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} labelledBy="confirm-title">
      <div className="flex flex-col gap-1.5">
        <div id="confirm-title" className="text-[17px] font-semibold">
          {title}
        </div>
        <div className="text-[13.5px] leading-[1.55] text-muted">{body}</div>
      </div>
      {error && (
        <div className="text-[13px] text-err-text" role="alert">
          {error}
        </div>
      )}
      <div className="flex justify-end gap-2">
        <Button onClick={onClose} className="h-[38px] text-[13.5px]">
          Cancel
        </Button>
        <Button
          variant={danger ? 'danger' : 'primary'}
          onClick={onConfirm}
          disabled={busy}
          className="h-[38px] text-[13.5px]"
        >
          {busy ? 'Working…' : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
