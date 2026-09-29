import { useQuery, type QueryClient } from '@tanstack/react-query';

import { endpoints, streamSSE, type ChatDetail, type Message } from '../api/client';

type Body = Record<string, unknown>;

export const chatsKey = ['chats'] as const;
export const chatKey = (id: string) => ['chat', id] as const;

export function useChats() {
  return useQuery({ queryKey: chatsKey, queryFn: endpoints.chats });
}

export function useChat(id: string | undefined) {
  // The cache is updated live while answers stream; a background refetch mid-stream would replace
  // the in-progress answer with the server's copy (which doesn't have it yet). We resync after streams.
  return useQuery({
    queryKey: chatKey(id ?? ''),
    queryFn: () => endpoints.chat(id!),
    enabled: !!id,
    staleTime: Infinity,
  });
}

export interface ModelChoice {
  connection_id: string;
  model: string;
}

const PENDING = 'pending-answer';

function blankAnswer(id: string): Message {
  return {
    id, role: 'assistant', content: '', model: null, connection_id: null, connection_name: null, runtime: null,
    confidence: null, citations: [], followups: [], error: null, created_at: new Date().toISOString(),
    stage: 'searching',
  };
}

/**
 * Streams an answer into the React Query cache for the chat, so the thread survives route changes
 * (e.g. "/" → "/c/:id" right after the chat is created).
 */
function run(qc: QueryClient, chatId: string, path: string, body: Body, targetId: string) {
  void qc.cancelQueries({ queryKey: chatKey(chatId) });
  let rejected = false;
  const update = (fn: (m: Message) => Message) =>
    qc.setQueryData<ChatDetail>(chatKey(chatId), (old) =>
      old ? { ...old, messages: old.messages.map((m) => (m.id === targetId ? fn(m) : m)) } : old,
    );
  /** Put a finished message in place of the placeholder, or append it if the placeholder is gone. */
  const settle = (msg: Message) =>
    qc.setQueryData<ChatDetail>(chatKey(chatId), (old) => {
      if (!old) return old;
      if (old.messages.some((m) => m.id === targetId || m.id === msg.id)) {
        return { ...old, messages: old.messages.map((m) => (m.id === targetId || m.id === msg.id ? msg : m)) };
      }
      return { ...old, messages: [...old.messages, msg] };
    });
  return streamSSE(path, body, {
    onStart: (user) =>
      qc.setQueryData<ChatDetail>(chatKey(chatId), (old) =>
        old ? { ...old, messages: old.messages.map((m) => (m.id === 'pending-user' ? user : m)) } : old,
      ),
    onStatus: (stage) => update((m) => ({ ...m, stage })),
    onToken: (t) => update((m) => ({ ...m, content: m.content + t, stage: 'answering' })),
    onDone: (msg) => settle(msg),
    onFollowups: (id, followups) =>
      qc.setQueryData<ChatDetail>(chatKey(chatId), (old) =>
        old ? { ...old, messages: old.messages.map((m) => (m.id === id ? { ...m, followups } : m)) } : old,
      ),
    onUsage: (id, u) =>
      qc.setQueryData<ChatDetail>(chatKey(chatId), (old) =>
        old
          ? {
              ...old,
              messages: old.messages.map((m) =>
                m.id === id
                  ? { ...m, prompt_tokens: u.prompt_tokens, completion_tokens: u.completion_tokens, tokens_estimated: u.estimated }
                  : m,
              ),
            }
          : old,
      ),
    onError: (detail, msg) => {
      if (msg) {
        settle({ ...msg, error: detail });
        return;
      }
      // Rejected before anything was saved (e.g. no usable model): the server has neither the question nor an
      // answer, so a resync would erase both. Keep them on screen, under ids that can't clash with the next ask.
      rejected = true;
      const tag = Date.now();
      qc.setQueryData<ChatDetail>(chatKey(chatId), (old) =>
        old
          ? {
              ...old,
              messages: old.messages.map((m) =>
                m.id === targetId
                  ? { ...m, id: targetId === PENDING ? `failed-${tag}` : m.id, stage: undefined, error: detail }
                  : m.id === 'pending-user'
                    ? { ...m, id: `unsent-${tag}` }
                    : m,
              ),
            }
          : old,
      );
    },
  }).finally(() => {
    qc.invalidateQueries({ queryKey: chatsKey });
    // Resync with the server (real ids, title, saved follow-ups) unless another answer is streaming.
    if (!rejected && !isStreaming(qc.getQueryData<ChatDetail>(chatKey(chatId)))) {
      qc.invalidateQueries({ queryKey: chatKey(chatId) });
    }
  });
}

export function askInChat(qc: QueryClient, chatId: string, content: string, choice?: ModelChoice) {
  const now = new Date().toISOString();
  qc.setQueryData<ChatDetail>(chatKey(chatId), (old) => {
    const base = old ?? {
      chat: { id: chatId, title: content, kb_id: null, kb_name: null, message_count: 0, created_at: now, updated_at: now },
      messages: [],
    };
    const user: Message = { ...blankAnswer('pending-user'), role: 'user', content, stage: undefined };
    return { ...base, messages: [...base.messages, user, blankAnswer(PENDING)] };
  });
  return run(qc, chatId, `/chats/${chatId}/messages`, { content, ...(choice ?? {}) }, PENDING);
}

export function regenerate(qc: QueryClient, chatId: string, messageId: string, choice?: ModelChoice) {
  qc.setQueryData<ChatDetail>(chatKey(chatId), (old) =>
    old ? { ...old, messages: old.messages.map((m) => (m.id === messageId ? { ...blankAnswer(messageId) } : m)) } : old,
  );
  return run(qc, chatId, `/messages/${messageId}/regenerate`, { ...(choice ?? {}) }, messageId);
}

export const isStreaming = (d: ChatDetail | undefined) => !!d?.messages.some((m) => m.stage);
