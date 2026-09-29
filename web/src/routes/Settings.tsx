import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { endpoints, type WorkspaceSettings } from '../api/client';
import { Topbar } from '../components/AppShell';
import { IconChevronDown } from '../components/icons';
import { ConfirmDialog } from '../components/Modal';
import { Button, Card, EmptyNote, Page, PageHeader, Pill, Row, Section, Spinner, Toggle } from '../components/ui';
import { useConnections } from '../hooks/useConnections';
import { useKbs } from '../hooks/useKbs';

const settingsKey = ['settings'] as const;
type Patch = Parameters<typeof endpoints.patchSettings>[0];

function Stepper({
  value,
  onChange,
  step,
  min,
  max,
  disabled,
  label,
}: {
  value: number;
  onChange: (v: number) => void;
  step: number;
  min: number;
  max: number;
  disabled?: boolean;
  label: string;
}) {
  const btn = 'h-[34px] w-[34px] border-none bg-surface2 text-[16px] text-text disabled:opacity-40';
  return (
    <div className="flex items-center overflow-hidden rounded-[9px] border border-border" role="group" aria-label={label}>
      <button type="button" className={btn} disabled={disabled || value - step < min} onClick={() => onChange(value - step)} aria-label={`Decrease ${label}`}>
        −
      </button>
      <span className="w-16 text-center font-mono text-[13px]">{value}</span>
      <button type="button" className={btn} disabled={disabled || value + step > max} onClick={() => onChange(value + step)} aria-label={`Increase ${label}`}>
        +
      </button>
    </div>
  );
}

export default function Settings() {
  const qc = useQueryClient();
  const { data: conns } = useConnections();
  const { data: kbs } = useKbs();
  const { data: s, isLoading, error } = useQuery({ queryKey: settingsKey, queryFn: endpoints.settings });
  const [draft, setDraft] = useState<{ chunk_size: number; chunk_overlap: number; embedding_model: string } | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (s) setDraft({ chunk_size: s.chunk_size, chunk_overlap: s.chunk_overlap, embedding_model: s.embedding_model });
  }, [s]);

  const patch = useMutation({
    mutationFn: (b: Patch) => endpoints.patchSettings(b),
    onSuccess: (next) => {
      qc.setQueryData<WorkspaceSettings>(settingsKey, next);
      if (next.reindexing) {
        setNotice(`Re-indexing ${next.reindexing} document${next.reindexing === 1 ? '' : 's'}. Follow progress on each knowledge base's page.`);
        qc.invalidateQueries({ queryKey: ['kbs'] });
        qc.invalidateQueries({ queryKey: ['documents'] });
      }
      setConfirm(false);
    },
  });
  const reindexAll = useMutation({
    mutationFn: endpoints.reindexAll,
    onSuccess: (next) => {
      setNotice(`Re-indexing ${next.reindexing} document${next.reindexing === 1 ? '' : 's'}.`);
      qc.invalidateQueries({ queryKey: ['documents'] });
    },
  });

  const canEdit = s?.can_edit ?? false;
  const docCount = (kbs ?? []).reduce((n, k) => n + k.doc_count, 0);
  const pending =
    !!s && !!draft &&
    (draft.chunk_size !== s.chunk_size || draft.chunk_overlap !== s.chunk_overlap || draft.embedding_model !== s.embedding_model);
  const overlapTooBig = !!draft && draft.chunk_overlap >= draft.chunk_size / 2;
  const toggle = (k: 'hybrid' | 'rerank' | 'keep_local' | 'ocr') => (v: boolean) => canEdit && patch.mutate({ [k]: v });

  return (
    <>
      <Topbar title="Settings" />
      <Page>
        <PageHeader title="Settings" sub="Applies to every knowledge base in this workspace." />
        {isLoading && <Spinner />}
        {error && <div className="text-[13px] text-err-text">{error.message}</div>}
        {!canEdit && s && <div className="text-[13px] text-muted">Only the workspace owner can change settings.</div>}
        {notice && <div className="rounded-xl bg-accent-soft px-4 py-3 text-[13px] text-accent-text">{notice}</div>}
        {patch.error && <div className="rounded-xl bg-err-soft px-4 py-3 text-[13px] text-err-text">{patch.error.message}</div>}

        <Section title="Model providers" action={<Link to="/keys" className="text-[13px] font-medium">Manage</Link>}>
          {conns && conns.length === 0 && (
            <EmptyNote>
              No providers yet. <Link to="/keys">Add an API Base and key</Link> on the API keys screen.
            </EmptyNote>
          )}
          {conns && conns.length > 0 && (
            <Card>
              {conns.map((c) => (
                <Row key={c.id} title={c.name} sub={<span className="font-mono">{c.api_base}</span>}>
                  <Pill tone="ok">Connected · {c.models.length} models</Pill>
                </Row>
              ))}
            </Card>
          )}
        </Section>

        {s && draft && (
          <>
            <Section title="Embeddings">
              <Card>
                <Row title="Embedding model" sub="Runs on this server. Changing it re-indexes every document.">
                  <div className="relative min-w-[260px]">
                    <select
                      value={draft.embedding_model}
                      disabled={!canEdit}
                      onChange={(e) => setDraft({ ...draft, embedding_model: e.target.value })}
                      aria-label="Embedding model"
                      className="h-[38px] w-full appearance-none rounded-[9px] border border-border bg-surface pl-3 pr-[34px] font-mono text-[12.5px] text-text outline-none"
                    >
                      {Object.entries(s.embedding_models).map(([m, dims]) => (
                        <option key={m} value={m}>
                          {m} ({dims} dims)
                        </option>
                      ))}
                    </select>
                    <IconChevronDown className="pointer-events-none absolute right-3 top-3 text-muted" />
                  </div>
                </Row>
                <Row title="Vector store" sub="Stored on this server.">
                  <span className="font-mono text-[13px] text-muted">Chroma · {s.embedding_dims ?? '?'} dims</span>
                </Row>
              </Card>
            </Section>

            <Section title="Chunking and retrieval">
              <Card>
                <Row title="Chunk size" sub="Tokens per passage. Smaller chunks give more precise citations.">
                  <Stepper label="chunk size" value={draft.chunk_size} step={100} min={200} max={2000} disabled={!canEdit}
                    onChange={(v) => setDraft({ ...draft, chunk_size: v })} />
                </Row>
                <Row title="Overlap" sub="Tokens shared between neighbouring chunks.">
                  <Stepper label="overlap" value={draft.chunk_overlap} step={20} min={0} max={400} disabled={!canEdit}
                    onChange={(v) => setDraft({ ...draft, chunk_overlap: v })} />
                </Row>
                {pending && (
                  <div className="flex flex-wrap items-center gap-3 bg-warn-soft px-[18px] py-3 text-[13px] text-warn-text">
                    <span className="flex-1">
                      {overlapTooBig
                        ? 'Overlap must be less than half the chunk size.'
                        : `Applying this re-indexes ${docCount} document${docCount === 1 ? '' : 's'}.`}
                    </span>
                    <Button onClick={() => setDraft({ chunk_size: s.chunk_size, chunk_overlap: s.chunk_overlap, embedding_model: s.embedding_model })}>
                      Cancel
                    </Button>
                    <Button variant="primary" disabled={overlapTooBig || patch.isPending} onClick={() => setConfirm(true)}>
                      Apply and re-index
                    </Button>
                  </div>
                )}
                <Row title="Passages per answer" sub="Most chunks the model reads for one question (top-k). Weak matches are left out.">
                  <Stepper label="passages per answer" value={s.top_k} step={1} min={1} max={40} disabled={!canEdit || patch.isPending}
                    onChange={(v) => patch.mutate({ top_k: v })} />
                </Row>
                <Row
                  title="Context per answer"
                  sub="Most document text (tokens) sent with one question. Lowered automatically to fit the model's context window; in LM Studio, set Context Length when loading the model."
                >
                  <Stepper label="context per answer" value={s.context_tokens} step={2000} min={2000} max={64000} disabled={!canEdit || patch.isPending}
                    onChange={(v) => patch.mutate({ context_tokens: v })} />
                </Row>
                <Row title="Hybrid search" sub="Combine keyword (BM25) and vector search.">
                  <Toggle on={s.hybrid} onChange={toggle('hybrid')} label="Hybrid search" />
                </Row>
                <Row title="Rerank results" sub="Re-score retrieved passages before answering. Slower, more accurate.">
                  <Toggle on={s.rerank} onChange={toggle('rerank')} label="Rerank results" />
                </Row>
              </Card>
            </Section>

            <Section title="Privacy and processing">
              <Card>
                <Row title="Keep local knowledge bases local" sub="Block cloud models from answering over local knowledge bases.">
                  <Toggle on={s.keep_local} onChange={toggle('keep_local')} label="Keep local knowledge bases local" />
                </Row>
                <Row title="OCR for scanned PDFs" sub="Extract text from image-only pages. Needs OCRmyPDF on the server; uses more CPU.">
                  <Toggle on={s.ocr} onChange={toggle('ocr')} label="OCR for scanned PDFs" />
                </Row>
                <Row title="Re-index all documents" sub="Parse and embed everything again, e.g. after turning on OCR.">
                  <Button disabled={!canEdit || reindexAll.isPending} onClick={() => reindexAll.mutate()}>
                    Re-index now
                  </Button>
                </Row>
              </Card>
            </Section>

            <Section title="Answer prompt" action={<Link to="/prompt" className="text-[13px] font-medium">Edit</Link>}>
              <Card>
                <Row title="Workspace instructions" sub={s.custom_instructions ? s.custom_instructions.slice(0, 140) + (s.custom_instructions.length > 140 ? '…' : '') : 'None. Answers follow the built-in rules only.'} />
              </Card>
            </Section>

            <ConfirmDialog
              open={confirm}
              title="Re-index every document?"
              body={
                draft.embedding_model !== s.embedding_model
                  ? `All ${docCount} document${docCount === 1 ? '' : 's'} are embedded again with ${draft.embedding_model}. Answers can't find passages until re-indexing finishes (a model that isn't built in downloads first, which needs internet).`
                  : `All ${docCount} document${docCount === 1 ? '' : 's'} are split again with the new chunking. Search keeps using the old passages until each document finishes.`
              }
              confirmLabel="Apply and re-index"
              busy={patch.isPending}
              error={patch.error?.message}
              onConfirm={() =>
                patch.mutate({
                  ...(draft.chunk_size !== s.chunk_size ? { chunk_size: draft.chunk_size } : {}),
                  ...(draft.chunk_overlap !== s.chunk_overlap ? { chunk_overlap: draft.chunk_overlap } : {}),
                  ...(draft.embedding_model !== s.embedding_model ? { embedding_model: draft.embedding_model } : {}),
                })
              }
              onClose={() => setConfirm(false)}
            />
          </>
        )}
      </Page>
    </>
  );
}
