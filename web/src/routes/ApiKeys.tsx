import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';

import { endpoints, type Connection } from '../api/client';
import { Topbar } from '../components/AppShell';
import { IconChevronDown } from '../components/icons';
import { ConfirmDialog } from '../components/Modal';
import { Button, EmptyNote, Page, PageHeader, Pill, Section, Spinner, cx } from '../components/ui';
import { connectionsKey, useConnections } from '../hooks/useConnections';

const inputClass =
  'h-[42px] w-full min-w-0 rounded-[10px] border border-border bg-surface px-3 font-mono text-[14px] text-text outline-none focus:border-accent';

function AddConnection() {
  const qc = useQueryClient();
  const [base, setBase] = useState('');
  const [key, setKey] = useState('');
  const [showKey, setShowKey] = useState(false);

  const save = useMutation({
    mutationFn: () => endpoints.addConnection({ api_base: base.trim(), api_key: key.trim() }),
    onSuccess: (conn) => {
      qc.setQueryData<Connection[]>(connectionsKey, (old) => [...(old ?? []), conn]);
      setBase('');
      setKey('');
      setShowKey(false);
    },
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (base.trim() && !save.isPending) save.mutate();
  };
  const edit = (set: (v: string) => void) => (e: { target: { value: string } }) => {
    set(e.target.value);
    if (save.error) save.reset();
  };

  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-col gap-4 rounded-[14px] border border-border bg-surface p-5"
      aria-label="Add a connection"
    >
      <div className="text-[15px] font-semibold">Add a connection</div>
      <label className="flex flex-col gap-1.5 text-[13px] font-medium">
        API Base
        <input
          className={inputClass}
          value={base}
          onChange={edit(setBase)}
          placeholder="https://api.openai.com/v1"
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <label className="flex flex-col gap-1.5 text-[13px] font-medium">
        API Key
        <div className="flex gap-2">
          <input
            className={cx(inputClass, 'flex-1')}
            type={showKey ? 'text' : 'password'}
            value={key}
            onChange={edit(setKey)}
            placeholder="sk-…"
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={() => setShowKey((v) => !v)}
            className="h-[42px] shrink-0 rounded-[10px] border border-border bg-surface px-3 text-[13px] text-muted hover:text-text"
          >
            {showKey ? 'Hide' : 'Show'}
          </button>
        </div>
        <span className="text-[12px] font-normal text-muted">
          Not needed for local servers like LM Studio or Ollama. From Docker, reach them at{' '}
          <code className="font-mono">http://host.docker.internal:1234/v1</code> (LM Studio) or{' '}
          <code className="font-mono">:11434/v1</code> (Ollama).
        </span>
      </label>
      {save.error && (
        <div className="text-[12.5px] text-err-text" role="alert">
          {save.error.message}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={!base.trim() || save.isPending}
          className="h-10 rounded-[10px] border-none bg-accent px-5 text-[14px] font-semibold text-on-accent hover:brightness-[1.08] disabled:opacity-50"
        >
          {save.isPending ? 'Checking…' : 'Save'}
        </button>
        <span className="text-[12.5px] text-muted">Keys are encrypted and stored on this server only.</span>
      </div>
    </form>
  );
}

function ConnectionCard({ c }: { c: Connection }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const replace = (conn: Connection) =>
    qc.setQueryData<Connection[]>(connectionsKey, (old) => (old ?? []).map((x) => (x.id === conn.id ? conn : x)));

  const setModel = useMutation({ mutationFn: (m: string) => endpoints.setConnectionModel(c.id, m), onSuccess: replace });
  const refresh = useMutation({ mutationFn: () => endpoints.refreshConnection(c.id), onSuccess: replace });
  const remove = useMutation({
    mutationFn: () => endpoints.removeConnection(c.id),
    onSuccess: () => {
      setConfirm(false);
      qc.setQueryData<Connection[]>(connectionsKey, (old) => (old ?? []).filter((x) => x.id !== c.id));
    },
  });

  const hint =
    c.selected_model === 'auto'
      ? `Auto picks the best available model for each question${c.resolved_model ? ` (now: ${c.resolved_model})` : ''}.`
      : `Always answer with ${c.selected_model}.`;
  const err = setModel.error ?? refresh.error;

  return (
    <div className="flex flex-col gap-3.5 rounded-xl border border-border bg-surface px-[18px] py-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-[200px] flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14px] font-semibold">{c.name}</span>
            <Pill tone="ok" className="px-2 py-0.5 text-[11.5px]">
              Connected · {c.models.length} models
            </Pill>
            <Pill tone={c.runtime === 'local' ? 'ok' : 'accent'} className="px-2 py-0.5 text-[11.5px]">
              {c.runtime === 'local' ? 'Local' : 'Cloud'}
            </Pill>
          </div>
          <span className="break-all font-mono text-[12.5px] text-muted">{c.api_base}</span>
          <span className="font-mono text-[12.5px] text-muted">{c.masked_key}</span>
        </div>
        <div className="flex gap-2">
          <Button className="h-8" onClick={() => refresh.mutate()} disabled={refresh.isPending} title="Re-list models">
            {refresh.isPending ? 'Refreshing…' : 'Refresh models'}
          </Button>
          <Button variant="danger" className="h-8" onClick={() => (remove.reset(), setConfirm(true))}>
            Remove
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3.5">
        <div className="min-w-[180px] flex-1">
          <div className="text-[13.5px] font-medium">Model</div>
          <div className="text-[12.5px] text-muted">{hint}</div>
        </div>
        <div className="relative min-w-[220px]">
          <select
            value={c.selected_model}
            onChange={(e) => setModel.mutate(e.target.value)}
            disabled={setModel.isPending}
            aria-label={`Model for ${c.name}`}
            className="h-[38px] w-full appearance-none rounded-[9px] border border-border bg-surface pl-3 pr-[34px] text-[13.5px] text-text outline-none"
          >
            <option value="auto">Auto (recommended)</option>
            {c.chat_models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <IconChevronDown className="pointer-events-none absolute right-3 top-3 text-muted" />
        </div>
      </div>
      {err && <div className="text-[12.5px] text-err-text">{err.message}</div>}
      <ConfirmDialog
        open={confirm}
        title={`Remove ${c.name}?`}
        body={
          <>
            The saved key for <span className="font-mono">{c.api_base}</span> is deleted from this server. You can add it
            again later.
          </>
        }
        confirmLabel="Remove"
        danger
        busy={remove.isPending}
        error={remove.error?.message}
        onConfirm={() => remove.mutate()}
        onClose={() => setConfirm(false)}
      />
    </div>
  );
}

export default function ApiKeys() {
  const { data: conns, isLoading, error } = useConnections();

  return (
    <>
      <Topbar title="API keys" />
      <Page>
        <PageHeader
          title="API keys"
          sub="Connect a model provider. Any OpenAI-compatible endpoint works, including Ollama, LM Studio, OpenAI, Anthropic, OpenRouter and vLLM."
        />
        <AddConnection />
        <Section title="Connected providers">
          {isLoading && <Spinner />}
          {error && <div className="text-[13px] text-err-text">{error.message}</div>}
          {conns && conns.length === 0 && <EmptyNote>No providers yet. Add an API Base and key above.</EmptyNote>}
          {conns?.map((c) => <ConnectionCard key={c.id} c={c} />)}
        </Section>
      </Page>
    </>
  );
}
