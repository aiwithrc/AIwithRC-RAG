import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { endpoints, isProcessing, type Doc } from '../api/client';
import { Topbar } from '../components/AppShell';
import { DropZone } from '../components/DropZone';
import { IconChat, IconClose, IconUpload } from '../components/icons';
import { EditKbDialog } from '../components/KbDialogs';
import { ConfirmDialog } from '../components/Modal';
import { Button, Page, Pill, Spinner, cx } from '../components/ui';
import { docsKey, useDocuments, useUpload } from '../hooks/useDocuments';
import { useKbs } from '../hooks/useKbs';
import { useIsMobile } from '../hooks/useMediaQuery';

const STATUS: Record<Doc['status'], { label: string; tone: 'ok' | 'err' | 'accent' | 'neutral' }> = {
  queued: { label: 'Queued', tone: 'neutral' },
  parsing: { label: 'Parsing', tone: 'accent' },
  chunking: { label: 'Chunking', tone: 'accent' },
  embedding: { label: 'Embedding', tone: 'accent' },
  indexed: { label: 'Indexed', tone: 'ok' },
  failed: { label: 'Failed', tone: 'err' },
};

function DocRow({ d, cols, mobile }: { d: Doc; cols: string; mobile: boolean }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: docsKey(d.kb_id) });
  const retry = useMutation({ mutationFn: () => endpoints.retryDocument(d.id), onSuccess: refresh });
  const del = useMutation({
    mutationFn: () => endpoints.deleteDocument(d.id),
    onSuccess: () => {
      setConfirm(false);
      qc.setQueryData<Doc[]>(docsKey(d.kb_id), (old) => (old ?? []).filter((x) => x.id !== d.id));
      qc.invalidateQueries({ queryKey: ['kbs'] });
    },
  });
  const s = STATUS[d.status];
  const proc = isProcessing(d) && d.status !== 'queued';

  return (
    <div className="group grid items-center gap-4 border-b border-border px-[18px] py-[13px] last:border-b-0" style={{ gridTemplateColumns: cols }}>
      <div className="flex min-w-0 items-center gap-[11px]">
        <span className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-lg bg-surface2 font-mono text-[9.5px] font-semibold text-muted">
          {d.type}
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          {d.status === 'indexed' ? (
            <a
              href={`/api/documents/${d.id}/file`}
              target="_blank"
              rel="noreferrer"
              className="truncate font-mono text-[13px] text-text hover:text-accent-text"
              title="Open document"
            >
              {d.filename}
            </a>
          ) : (
            <span className="truncate font-mono text-[13px]">{d.filename}</span>
          )}
          {d.error && <span className="text-[12px] text-err-text">{d.error}</span>}
          {mobile && <span className="text-[12px] text-muted">{d.size}</span>}
        </div>
      </div>
      {!mobile && <span className="text-[13px] text-muted">{d.size}</span>}
      {!mobile && <span className="font-mono text-[13px] text-muted">{d.chunk_count || '—'}</span>}
      <div className="flex items-center gap-2">
        <div className="flex min-w-0 flex-1 flex-col items-start gap-1.5">
          <Pill tone={s.tone}>{proc ? `${s.label} · ${d.progress}%` : s.label}</Pill>
          {proc && (
            <div className="h-1 w-full max-w-[140px] overflow-hidden rounded-full bg-surface2">
              <div className="h-full bg-accent transition-[width] duration-300" style={{ width: `${d.progress}%` }} />
            </div>
          )}
          {d.status === 'failed' && (
            <button
              type="button"
              onClick={() => retry.mutate()}
              disabled={retry.isPending}
              className="border-none bg-transparent p-0 text-[12px] font-medium text-accent-text"
            >
              Retry
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => (del.reset(), setConfirm(true))}
          aria-label={`Delete ${d.filename}`}
          title="Delete"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border-none bg-transparent text-muted opacity-60 hover:bg-err-soft hover:text-err-text group-hover:opacity-100"
        >
          <IconClose size={14} />
        </button>
      </div>
      <ConfirmDialog
        open={confirm}
        title={`Delete ${d.filename}?`}
        body="The file and its passages are removed from this knowledge base. Answers that already cited it keep their snapshot."
        confirmLabel="Delete"
        danger
        busy={del.isPending}
        error={del.error?.message}
        onConfirm={() => del.mutate()}
        onClose={() => setConfirm(false)}
      />
    </div>
  );
}

export default function KbDetail() {
  const { id } = useParams();
  const { data: kbs, isLoading } = useKbs();
  const docsQ = useDocuments(id);
  const upload = useUpload(id);
  const mobile = useIsMobile();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const kb = kbs?.find((k) => k.id === id);
  const docs = docsQ.data ?? [];
  const cols = mobile ? 'minmax(0,1fr) auto' : 'minmax(0,1fr) 90px 70px 170px';
  const indexed = docs.filter((d) => d.status === 'indexed').length;
  const rejected = !dismissed ? upload.data?.rejected ?? [] : [];

  return (
    <>
      <Topbar title={kb?.name ?? 'Knowledge base'} />
      <Page width={1080}>
        <Link to="/kbs" className="-mb-2 self-start text-[13px] text-muted hover:text-text hover:no-underline">
          ← Knowledge bases
        </Link>
        {isLoading && <Spinner />}
        {!isLoading && !kb && <div className="text-muted">This knowledge base doesn't exist or was deleted.</div>}
        {kb && (
          <>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex min-w-0 flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2.5">
                  <h1 className="m-0 text-[26px] font-semibold tracking-[-0.02em]">{kb.name}</h1>
                  <Pill tone={kb.runtime === 'local' ? 'ok' : 'accent'}>{kb.runtime === 'local' ? 'Local' : 'Cloud'}</Pill>
                  <button
                    type="button"
                    onClick={() => setEditing(true)}
                    className="border-none bg-transparent p-0 text-[13px] font-medium text-muted hover:text-text"
                  >
                    Edit
                  </button>
                </div>
                {kb.description && <div className="text-[14px] text-muted">{kb.description}</div>}
                <div className="text-[13px] text-muted">
                  {indexed} of {docs.length} documents indexed
                </div>
              </div>
              <Button
                variant="primary"
                className="h-[38px] text-[14px]"
                onClick={() => navigate('/', { state: { kbId: kb.id, fresh: Date.now() } })}
              >
                <IconChat />
                Chat with this knowledge base
              </Button>
            </div>

            <DropZone
              onFiles={(files) => {
                setDismissed(false);
                upload.mutate(files);
              }}
              disabled={upload.isPending}
              className="flex flex-col items-center gap-2.5 rounded-[14px] bg-surface px-5 py-[30px]"
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-[11px] bg-accent-soft text-accent-text">
                {upload.isPending ? <Spinner /> : <IconUpload size={20} />}
              </div>
              <div className="text-[14.5px] font-semibold">
                {upload.isPending ? 'Uploading…' : 'Drop files here or click to upload'}
              </div>
              <div className="text-[13px] text-muted">PDF, DOCX, MD, TXT, CSV, XLSX · up to 50 MB each</div>
            </DropZone>

            {(upload.error || rejected.length > 0) && (
              <div className="flex flex-col gap-1 rounded-xl bg-err-soft px-4 py-3 text-[13px] text-err-text" role="alert">
                <div className="flex items-start justify-between gap-3">
                  <div className="font-medium">
                    {upload.error ? upload.error.message : `${rejected.length} file${rejected.length === 1 ? " wasn't" : "s weren't"} added`}
                  </div>
                  <button
                    type="button"
                    onClick={() => (setDismissed(true), upload.reset())}
                    aria-label="Dismiss"
                    className="border-none bg-transparent p-0 text-err-text"
                  >
                    <IconClose size={14} />
                  </button>
                </div>
                {rejected.map((r) => (
                  <div key={r.filename}>
                    <span className="font-mono">{r.filename}</span>: {r.reason}
                  </div>
                ))}
              </div>
            )}

            <div className="overflow-hidden rounded-[14px] border border-border bg-surface">
              <div
                className="grid gap-4 border-b border-border px-[18px] py-[11px] text-[12px] font-medium text-muted"
                style={{ gridTemplateColumns: cols }}
              >
                <span>Document</span>
                {!mobile && <span>Size</span>}
                {!mobile && <span>Chunks</span>}
                <span>Status</span>
              </div>
              {docsQ.isLoading && (
                <div className="p-6">
                  <Spinner />
                </div>
              )}
              {docsQ.data && docs.length === 0 && (
                <div className={cx('px-[18px] py-8 text-center text-[13.5px] text-muted')}>
                  No documents yet. Upload a file to start indexing.
                </div>
              )}
              {docs.map((d) => (
                <DocRow key={d.id} d={d} cols={cols} mobile={mobile} />
              ))}
            </div>
            <EditKbDialog kb={kb} open={editing} onClose={() => setEditing(false)} />
          </>
        )}
      </Page>
    </>
  );
}
