import { useRef, useState, type ReactNode } from 'react';

import { ACCEPT } from '../hooks/useDocuments';
import { cx } from './ui';

/**
 * Click-or-drop file picker. Renders `children` inside a dashed box that highlights while
 * files are dragged over it. Calls `onFiles` with every dropped/chosen file.
 */
export function DropZone({
  onFiles,
  disabled,
  className,
  children,
  multiple = true,
}: {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
  multiple?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const depth = useRef(0);

  const take = (list: FileList | null) => {
    const files = Array.from(list ?? []);
    if (files.length && !disabled) onFiles(multiple ? files : files.slice(0, 1));
  };

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragEnter={(e) => {
          e.preventDefault();
          depth.current += 1;
          setOver(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => {
          depth.current = Math.max(0, depth.current - 1);
          if (depth.current === 0) setOver(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          depth.current = 0;
          setOver(false);
          take(e.dataTransfer.files);
        }}
        className={cx(
          'w-full cursor-pointer border-[1.5px] border-dashed text-text transition-colors hover:border-accent hover:bg-accent-soft disabled:cursor-default disabled:opacity-60',
          over ? 'border-accent bg-accent-soft' : 'border-border-strong',
          className,
        )}
      >
        {children}
      </button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple={multiple}
        hidden
        onChange={(e) => {
          take(e.target.files);
          e.target.value = '';
        }}
      />
    </>
  );
}
