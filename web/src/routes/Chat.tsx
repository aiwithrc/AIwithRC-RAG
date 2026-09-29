import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { endpoints, type ChatDetail, type Kb } from '../api/client';
import { Topbar } from '../components/AppShell';
import { KbPicker, ModelPicker, useModelChoice } from '../components/chat/Pickers';
import { SourcePanel } from '../components/chat/SourcePanel';
import { Thread, type ActiveSource } from '../components/chat/Thread';
import { DropZone } from '../components/DropZone';
import { IconArrowUp, IconLock, IconUpload } from '../components/icons';
import { Pill, Spinner, cx } from '../components/ui';
import { askInChat, chatKey, chatsKey, isStreaming, regenerate, useChat } from '../hooks/useChat';
import { ACCEPT, stageLabel, useDocuments, useUpload } from '../hooks/useDocuments';
import { useKbs } from '../hooks/useKbs';
import { useIsMobile } from '../hooks/useMediaQuery';
import { useMe } from '../hooks/useMe';

function PrivacyPill({ cloud, provider }: { cloud: boolean; provider?: string }) {
  return cloud ? (
    <Pill tone="warn" className="px-[11px] py-[5px] text-[12.5px]">
      <IconLock />
      Uses {provider ?? 'a cloud provider'} · passages sent via API
    </Pill>
  ) : (
    <Pill tone="ok" className="px-[11px] py-[5px] text-[12.5px]">
      <IconLock />
      Private · runs on your server
    </Pill>
  );
}

function SendButton({ enabled }: { enabled: boolean }) {
  return (
    <button
      type="submit"
      disabled={!enabled}
      aria-label="Send"
      className={cx(
        'flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] border-none bg-accent text-on-accent',
        enabled ? 'opacity-100' : 'opacity-45',
      )}
    >
      <IconArrowUp />
    </button>
  );
}

/** Empty chat: hero, composer, drop-to-index and quick upload progress. */
function EmptyChat({
  kb,
  cloud,
  provider,
  noModel,
  onAsk,
  error,
}: {
  kb?: Kb;
  cloud: boolean;
  provider?: string;
  noModel: boolean;
  onAsk: (q: string) => void;
  error: string | null;
}) {
  const mobile = useIsMobile();
  const [draft, setDraft] = useState('');
  const [quickId, setQuickId] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const kbName = kb?.name ?? 'your documents';
  const upload = useUpload(kb?.id);
  const { data: kbDocs } = useDocuments(quickId ? kb?.id : undefined);
  const quick = quickId ? kbDocs?.find((d) => d.id === quickId) : undefined;
  const startUpload = (files: File[]) => upload.mutate(files, { onSuccess: (res) => setQuickId(res.documents[0]?.id ?? null) });
  const rejected = upload.data?.rejected ?? [];
  const canSend = !!draft.trim() && !!kb && !noModel;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (canSend) onAsk(draft.trim());
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
      <div className="mx-auto flex max-w-[680px] flex-col gap-[22px] px-4 pb-10 min-[820px]:px-8" style={{ paddingTop: mobile ? 40 : '11vh' }}>
        <div className="flex flex-col items-center gap-3 text-center">
          <PrivacyPill cloud={cloud} provider={provider} />
          <h1 className="m-0 font-semibold leading-[1.1] tracking-[-0.025em] text-balance" style={{ fontSize: mobile ? 28 : 38 }}>
            Ask your documents anything
          </h1>
          <p className="m-0 max-w-[460px] text-[15.5px] leading-[1.55] text-muted text-pretty">
            Answers cite the exact passage they came from, so you can check every claim.
          </p>
        </div>

        <form onSubmit={submit} className="flex flex-col gap-1.5 rounded-2xl border border-border bg-surface py-2.5 pl-4 pr-2.5 shadow-card">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={`Ask anything about ${kbName}…`}
            aria-label="Question"
            autoFocus={!mobile}
            className="w-full border-none bg-transparent py-2 text-[15.5px] text-text outline-none"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              disabled={!kb || upload.isPending}
              className="flex h-[30px] items-center gap-1.5 rounded-lg border border-border bg-transparent pl-2 pr-2.5 text-[12.5px] text-muted hover:bg-surface2 hover:text-text"
            >
              <IconUpload size={14} />
              Add file
            </button>
            <input
              ref={fileInput}
              type="file"
              accept={ACCEPT}
              hidden
              onChange={(e) => {
                const f = Array.from(e.target.files ?? []);
                if (f.length) startUpload(f.slice(0, 1));
                e.target.value = '';
              }}
            />
            <div className="flex-1" />
            <SendButton enabled={canSend} />
          </div>
        </form>
        {noModel && (
          <div className="rounded-xl bg-warn-soft px-4 py-3 text-[13px] text-warn-text">
            Connect a model to get answers. <Link to="/keys">Add one on the API keys screen</Link>.
          </div>
        )}
        {error && (
          <div className="rounded-xl bg-err-soft px-4 py-3 text-[13px] text-err-text" role="alert">
            {error}
          </div>
        )}

        {quick ? (
          <div className="flex items-center gap-3.5 rounded-[14px] border border-border bg-surface px-4 py-3.5">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-surface2 font-mono text-[10.5px] font-semibold text-muted">
              {quick.type}
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-[7px]">
              <div className="flex justify-between gap-2.5">
                <span className="truncate font-mono text-[13.5px] font-medium">{quick.filename}</span>
                <span
                  className={cx(
                    'whitespace-nowrap text-[12.5px]',
                    quick.status === 'indexed' ? 'text-ok-text' : quick.status === 'failed' ? 'text-err-text' : 'text-muted',
                  )}
                >
                  {quick.status === 'indexed' ? 'Ready' : quick.status === 'failed' ? 'Failed' : `${quick.progress}%`}
                </span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-surface2">
                <div
                  className={cx(
                    'h-full rounded-full transition-[width] duration-300',
                    quick.status === 'indexed' ? 'bg-ok' : quick.status === 'failed' ? 'bg-err-text' : 'bg-accent',
                  )}
                  style={{ width: `${quick.status === 'failed' ? 100 : quick.progress}%` }}
                />
              </div>
              <div className={cx('flex flex-wrap gap-x-2 text-[12.5px]', quick.status === 'failed' ? 'text-err-text' : 'text-muted')}>
                <span>{stageLabel(quick, kb?.runtime !== 'cloud')}</span>
                {(quick.status === 'indexed' || quick.status === 'failed') && (
                  <button type="button" onClick={() => setQuickId(null)} className="border-none bg-transparent p-0 text-[12.5px] font-medium text-accent-text">
                    Add another
                  </button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <DropZone
            onFiles={(files) => startUpload(files.slice(0, 1))}
            multiple={false}
            disabled={!kb || upload.isPending}
            className="flex items-center gap-3.5 rounded-[14px] bg-transparent p-[18px] text-left"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-accent-soft text-accent-text">
              <IconUpload size={18} />
            </div>
            <div className="flex min-w-0 flex-col gap-[3px]">
              <div className="text-[14px] font-semibold">{upload.isPending ? 'Uploading…' : 'Drop a document to start'}</div>
              <div className="text-[13px] text-muted">PDF, DOCX, MD, TXT, CSV or XLSX. Indexed into {kbName} in seconds.</div>
            </div>
          </DropZone>
        )}
        {(upload.error || rejected.length > 0) && (
          <div className="rounded-xl bg-err-soft px-4 py-3 text-[13px] text-err-text" role="alert">
            {upload.error?.message ?? rejected.map((r) => `${r.filename}: ${r.reason}`).join(' ')}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Chat() {
  const { chatId } = useParams();
  const { data: me } = useMe();
  const { data: kbs } = useKbs();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const model = useModelChoice();
  const { data: detail, isLoading, error: loadError } = useChat(chatId);

  const [kbId, setKbId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [startError, setStartError] = useState<string | null>(null);
  const [active, setActive] = useState<ActiveSource | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  // "New chat" resets to the user's default KB, or to the KB we were sent here with.
  const navState = location.state as { fresh?: number; kbId?: string } | null;
  useEffect(() => {
    setKbId(navState?.kbId ?? null);
    setDraft('');
    setStartError(null);
  }, [navState?.fresh]);
  useEffect(() => setActive(null), [chatId]);

  const chatKb = detail?.chat.kb_id ? kbs?.find((k) => k.id === detail.chat.kb_id) : undefined;
  const pickedKb = kbs?.find((k) => k.id === kbId) ?? kbs?.find((k) => k.id === me?.default_kb_id) ?? kbs?.[0];
  const kb = chatId ? chatKb : pickedKb;
  const kbName = kb?.name ?? detail?.chat.kb_name ?? 'this knowledge base';
  const current = model.current;
  const cloud = current ? current.conn.runtime === 'cloud' : kb?.runtime === 'cloud';
  const busy = isStreaming(detail);
  const messages = detail?.messages ?? [];

  // Keep the newest message in view while it streams (unless the reader scrolled up).
  const lastLen = messages.length ? messages[messages.length - 1].content.length : 0;
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
  }, [messages.length, lastLen]);

  const startChat = async (q: string) => {
    if (!kb) return;
    setStartError(null);
    try {
      const chat = await endpoints.createChat(kb.id);
      qc.setQueryData<ChatDetail>(chatKey(chat.id), { chat, messages: [] });
      qc.invalidateQueries({ queryKey: chatsKey });
      navigate(`/c/${chat.id}`);
      void askInChat(qc, chat.id, q, model.choice);
    } catch (e) {
      setStartError((e as Error).message);
    }
  };

  const followUp = (q: string) => {
    if (!chatId || busy) return;
    setDraft('');
    void askInChat(qc, chatId, q, model.choice);
  };

  const activeMsg = active ? messages.find((m) => m.id === active.messageId) : undefined;
  const title = chatId ? detail?.chat.title ?? 'Chat' : 'New chat';

  return (
    <>
      <Topbar title={title}>
        <KbPicker kbs={kbs ?? []} kb={kb} onSelect={setKbId} disabled={!!chatId} />
        <ModelPicker m={model} />
      </Topbar>

      {!chatId ? (
        <EmptyChat
          kb={kb}
          cloud={!!cloud}
          provider={current?.conn.name}
          noModel={model.loaded && !current}
          onAsk={startChat}
          error={startError}
        />
      ) : (
        <div className="relative flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
              {isLoading && (
                <div className="p-8">
                  <Spinner />
                </div>
              )}
              {loadError && <div className="p-8 text-muted">This chat doesn't exist or was deleted.</div>}
              {detail && (
                <Thread
                  messages={messages}
                  kbName={kbName}
                  busy={busy}
                  active={active}
                  onCite={(messageId, n) => setActive({ messageId, n })}
                  onFollow={followUp}
                  onRegenerate={(id) => !busy && void regenerate(qc, chatId, id, model.choice)}
                />
              )}
            </div>
            {detail && (
              <div className="shrink-0 px-4 pb-3.5 min-[820px]:px-8">
                <div className="mx-auto flex max-w-[760px] flex-col gap-2">
                  {current?.conn.runtime === 'cloud' && kb?.runtime === 'local' && (
                    <div className="rounded-[9px] bg-warn-soft px-3 py-2 text-[12.5px] text-warn-text">
                      {current.model.split('/').pop()} is a cloud model. Retrieved passages from {kbName} will be sent to{' '}
                      {current.conn.name}.
                    </div>
                  )}
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (draft.trim()) followUp(draft.trim());
                    }}
                    className="flex items-center gap-2 rounded-[14px] border border-border bg-surface py-1.5 pl-4 pr-1.5 shadow-card"
                  >
                    <input
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      placeholder="Ask a follow-up…"
                      aria-label="Follow-up question"
                      className="min-w-0 flex-1 border-none bg-transparent py-[9px] text-[15px] text-text outline-none"
                    />
                    <SendButton enabled={!!draft.trim() && !busy && !!current} />
                  </form>
                  <div className="text-center text-[12px] text-muted">
                    {cloud ? `Uses ${current?.conn.name ?? 'a cloud provider'} · passages sent via API` : 'Private · runs on your server'} ·
                    Check citations before relying on an answer.
                  </div>
                </div>
              </div>
            )}
          </div>
          {activeMsg && activeMsg.citations.length > 0 && active && (
            <SourcePanel
              citations={activeMsg.citations}
              active={active.n}
              kbName={kbName}
              onSelect={(n) => setActive({ messageId: activeMsg.id, n })}
              onClose={() => setActive(null)}
            />
          )}
        </div>
      )}
    </>
  );
}
