import { useState } from 'react';

import type { Message } from '../../api/client';
import { IconPlus, IconSearch } from '../icons';
import { Pill, Spinner, cx } from '../ui';
import { AnswerText, answerForClipboard } from './Answer';

export interface ActiveSource {
  messageId: string;
  n: number;
}

const STAGE: Record<NonNullable<Message['stage']>, string> = {
  searching: 'Searching {kb} for relevant passages…',
  thinking: 'Thinking…',
  answering: '',
};

function CopyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function ShareIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function RegenIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12a9 9 0 1 1-3-6.7L21 8" />
      <path d="M21 3v5h-5" />
    </svg>
  );
}

function AssistantMessage({
  m,
  kbName,
  isLast,
  busy,
  active,
  onCite,
  onFollow,
  onRegenerate,
  onShare,
}: {
  m: Message;
  kbName: string;
  isLast: boolean;
  busy: boolean;
  active: ActiveSource | null;
  onCite: (n: number) => void;
  onFollow: (q: string) => void;
  onRegenerate: () => void;
  onShare: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const activeN = active?.messageId === m.id ? active.n : null;
  const streaming = !!m.stage;
  const status = m.stage && STAGE[m.stage] ? STAGE[m.stage].replace('{kb}', kbName) : '';

  if (streaming && !m.content) {
    return (
      <div className="flex items-center gap-2.5 text-[14px] text-muted" role="status">
        <div className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] bg-accent-soft text-accent-text">
          {m.stage === 'searching' ? <IconSearch size={14} /> : <Spinner className="h-3.5 w-3.5" />}
        </div>
        {status || 'Writing…'}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] bg-accent font-mono text-[10px] font-semibold text-on-accent">
          RC
        </div>
        {m.model && <span className="text-[13px] text-muted">{m.model.split('/').pop()}</span>}
        {m.confidence === 'high' && (
          <Pill tone="ok">
            High confidence · {m.citations.length} source{m.citations.length === 1 ? '' : 's'}
          </Pill>
        )}
        {m.confidence === 'low' && <Pill tone="warn">Low confidence · partial match</Pill>}
        {streaming && <Spinner className="h-3.5 w-3.5" />}
      </div>

      {m.content && (
        <AnswerText
          text={m.content}
          active={activeN}
          onCite={streaming ? undefined : onCite}
          className="text-[15.5px] leading-[1.72]"
        />
      )}

      {m.error && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-err-soft px-4 py-3 text-[13.5px] text-err-text" role="alert">
          <span className="flex-1">{m.error}</span>
          <button
            type="button"
            onClick={onRegenerate}
            disabled={busy}
            className="border-none bg-transparent p-0 text-[13px] font-semibold text-err-text underline disabled:opacity-50"
          >
            Try again
          </button>
        </div>
      )}

      {m.citations.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {m.citations.map((c) => {
            const on = activeN === c.n;
            return (
              <button
                key={c.n}
                type="button"
                onClick={() => onCite(c.n)}
                className={cx(
                  'flex min-w-0 max-w-full items-center gap-2 rounded-[9px] border px-2.5 py-[7px] text-text hover:border-accent',
                  on ? 'border-accent bg-accent-soft' : 'border-border bg-surface',
                )}
              >
                <span className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[5px] bg-accent-soft font-mono text-[10.5px] font-semibold text-accent-text">
                  {c.n}
                </span>
                <span className="max-w-[180px] truncate font-mono text-[12px]">{c.filename}</span>
                {(c.page != null || c.section) && (
                  <span className="whitespace-nowrap text-[12px] text-muted">
                    {c.page != null ? `p. ${c.page}` : (c.section ?? '').split(' › ').pop()?.slice(0, 28)}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {!streaming && m.content && (
        <div className="-ml-2 flex gap-0.5">
          <button
            type="button"
            onClick={() => {
              navigator.clipboard?.writeText(answerForClipboard(m.content, m.citations)).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1400);
              });
            }}
            className="flex h-[30px] items-center gap-1.5 rounded-[7px] border-none bg-transparent px-2 text-[12.5px] text-muted hover:bg-surface2 hover:text-text"
          >
            <CopyIcon />
            {copied ? 'Copied' : 'Copy'}
          </button>
          {!m.id.startsWith('pending') && (
            <button
              type="button"
              onClick={onShare}
              className="flex h-[30px] items-center gap-1.5 rounded-[7px] border-none bg-transparent px-2 text-[12.5px] text-muted hover:bg-surface2 hover:text-text"
            >
              <ShareIcon />
              Share
            </button>
          )}
          <button
            type="button"
            onClick={onRegenerate}
            disabled={busy}
            className="flex h-[30px] items-center gap-1.5 rounded-[7px] border-none bg-transparent px-2 text-[12.5px] text-muted hover:bg-surface2 hover:text-text disabled:opacity-50"
          >
            <RegenIcon />
            Regenerate
          </button>
          <TokenCount m={m} className="ml-auto" />
        </div>
      )}

      {isLast && !streaming && m.followups.length > 0 && (
        <div className="flex flex-col border-t border-border">
          {m.followups.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => onFollow(q)}
              disabled={busy}
              className="flex items-center justify-between gap-3 border-x-0 border-b border-t-0 border-border bg-transparent px-0.5 py-[11px] text-left text-[14px] text-text hover:text-accent-text disabled:opacity-50"
            >
              {q}
              <IconPlus size={15} className="shrink-0 text-muted" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const fmt = (n: number) => n.toLocaleString();

/** "~1,234 tokens" with the in/out split on hover and for screen readers. "~" marks a local estimate. */
function TokenCount({ m, className }: { m: Message; className?: string }) {
  if (m.prompt_tokens == null || m.completion_tokens == null) return null;
  const total = m.prompt_tokens + m.completion_tokens;
  const approx = m.tokens_estimated ? '~' : '';
  const detail = `${approx}${fmt(m.prompt_tokens)} in (question, passages, chat) · ${approx}${fmt(m.completion_tokens)} out (answer)${m.tokens_estimated ? ' · estimated: the model server did not report its own count' : ''}`;
  return (
    <span className={cx('whitespace-nowrap font-mono text-[11.5px] text-muted', className)} title={detail} aria-label={`Tokens used: ${detail}`}>
      {approx}
      {fmt(total)} tokens
    </span>
  );
}

/** Running total for the whole chat, under the last message. */
function ChatTokens({ messages }: { messages: Message[] }) {
  const used = messages.filter((m) => m.role === 'assistant' && m.prompt_tokens != null && m.completion_tokens != null);
  if (!used.length || messages.some((m) => m.stage)) return null;
  const input = used.reduce((n, m) => n + (m.prompt_tokens ?? 0), 0);
  const output = used.reduce((n, m) => n + (m.completion_tokens ?? 0), 0);
  const approx = used.some((m) => m.tokens_estimated) ? '~' : '';
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-2 border-t border-border pt-3 text-center text-[12px] text-muted">
      <span>
        This chat used <span className="font-mono text-text">{approx}{fmt(input + output)}</span> tokens
      </span>
      <span className="font-mono">
        ({approx}{fmt(input)} in · {approx}{fmt(output)} out · {used.length} answer{used.length === 1 ? '' : 's'})
      </span>
    </div>
  );
}

export function Thread({
  messages,
  kbName,
  busy,
  active,
  onCite,
  onFollow,
  onRegenerate,
  onShare,
}: {
  messages: Message[];
  kbName: string;
  busy: boolean;
  active: ActiveSource | null;
  onCite: (messageId: string, n: number) => void;
  onFollow: (q: string) => void;
  onRegenerate: (messageId: string) => void;
  onShare: (messageId: string) => void;
}) {
  return (
    <div className="mx-auto flex max-w-[760px] flex-col gap-[30px] px-4 pb-6 pt-7 min-[820px]:px-8">
      {messages.map((m, i) =>
        m.role === 'user' ? (
          <div
            key={m.id}
            className="max-w-[82%] self-end whitespace-pre-wrap rounded-[16px_16px_4px_16px] bg-surface2 px-[15px] py-2.5 text-[15px] leading-[1.55]"
          >
            {m.content}
          </div>
        ) : (
          <AssistantMessage
            key={m.id}
            m={m}
            kbName={kbName}
            isLast={i === messages.length - 1}
            busy={busy}
            active={active}
            onCite={(n) => onCite(m.id, n)}
            onFollow={onFollow}
            onRegenerate={() => onRegenerate(m.id)}
            onShare={() => onShare(m.id)}
          />
        ),
      )}
      <ChatTokens messages={messages} />
    </div>
  );
}
