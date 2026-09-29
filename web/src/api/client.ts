/** Thin fetch wrapper for the JSON API. Sends the CSRF header on every request. */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Json = Record<string, unknown> | unknown[];

function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === 'string') return d;
    // FastAPI validation errors: [{msg: "Value error, Password needs…"}]
    if (Array.isArray(d) && d[0] && typeof d[0].msg === 'string') return d[0].msg.replace(/^Value error, /, '');
  }
  return fallback;
}

export async function api<T = unknown>(path: string, init: { method?: string; body?: Json } = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: init.method ?? 'GET',
    credentials: 'same-origin',
    headers: {
      'X-Requested-With': 'fetch',
      ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detailMessage(body, `Request failed (${res.status})`));
  return body as T;
}

// ---- Types (mirror api/app/schemas) ----

export type Theme = 'light' | 'dark';

export interface Me {
  id: string;
  email: string;
  name: string;
  role: 'owner' | 'member';
  theme: Theme;
  default_kb_id: string | null;
  workspace_id: string;
}

export interface AuthConfig {
  signup_open: boolean;
  has_users: boolean;
  public_host: string;
}

export interface SessionInfo {
  id: string;
  device: string;
  ip: string;
  created_at: string;
  last_seen_at: string;
  current: boolean;
}

export interface Kb {
  id: string;
  name: string;
  description: string;
  runtime: 'local' | 'cloud';
  default_model: string;
  default_connection_id: string | null;
  doc_count: number;
  indexed_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export type DocStatus = 'queued' | 'parsing' | 'chunking' | 'embedding' | 'indexed' | 'failed';

export interface Doc {
  id: string;
  kb_id: string;
  filename: string;
  type: string;
  size_bytes: number;
  size: string;
  status: DocStatus;
  progress: number;
  error: string | null;
  chunk_count: number;
  created_at: string;
}

export interface UploadResult {
  documents: Doc[];
  rejected: { filename: string; reason: string }[];
}

export const isProcessing = (d: Doc) => d.status !== 'indexed' && d.status !== 'failed';

/** Multipart upload (fetch sets the boundary; we only add the CSRF header). */
export async function uploadFiles(kbId: string, files: File[]): Promise<UploadResult> {
  const form = new FormData();
  files.forEach((f) => form.append('files', f, f.name));
  const res = await fetch(`/api/kbs/${kbId}/documents`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-Requested-With': 'fetch' },
    body: form,
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detailMessage(body, `Upload failed (${res.status})`));
  return body as UploadResult;
}

export interface Connection {
  id: string;
  name: string;
  api_base: string;
  masked_key: string;
  kind: 'openai_compat' | 'anthropic';
  runtime: 'local' | 'cloud';
  models: string[];
  chat_models: string[];
  selected_model: string; // 'auto' or a model id
  resolved_model: string | null;
  created_at: string;
}

export interface Citation {
  n: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page: number | null;
  section: string | null;
  location: string;
  score: number;
  chunk: number;
  total: number;
  before: string;
  hit: string;
  after: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  model: string | null;
  connection_id: string | null;
  connection_name: string | null;
  runtime: 'local' | 'cloud' | null;
  confidence: 'high' | 'low' | null;
  citations: Citation[];
  followups: string[];
  error: string | null;
  created_at: string;
  /** Client-only: set while the answer is streaming. */
  stage?: 'searching' | 'thinking' | 'answering';
}

export interface ChatSummary {
  id: string;
  title: string;
  kb_id: string | null;
  kb_name: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChatDetail {
  chat: ChatSummary;
  messages: Message[];
}

export interface StreamHandlers {
  onStart?: (user: Message) => void;
  onStatus?: (stage: 'searching' | 'thinking' | 'answering') => void;
  onToken?: (text: string) => void;
  onDone?: (message: Message) => void;
  onFollowups?: (messageId: string, followups: string[]) => void;
  onError?: (detail: string, message?: Message) => void;
}

/** POST that answers with Server-Sent Events (EventSource can't POST, so parse the stream by hand). */
export async function streamSSE(path: string, body: Json, h: StreamHandlers, signal?: AbortSignal): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch', 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal,
    });
  } catch {
    h.onError?.("Can't reach the server. Check your connection and try again.");
    return;
  }
  if (!res.ok || !res.body) {
    const b = await res.json().catch(() => null);
    h.onError?.(detailMessage(b, `Request failed (${res.status})`));
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let finished = false;
  const dispatch = (block: string) => {
    let event = 'message';
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += line.slice(5).trim();
    }
    if (!data) return;
    const d = JSON.parse(data);
    if (event === 'start') h.onStart?.(d.user);
    else if (event === 'status') h.onStatus?.(d.stage);
    else if (event === 'token') h.onToken?.(d.t);
    else if (event === 'done') {
      finished = true;
      h.onDone?.(d.message);
    } else if (event === 'followups') h.onFollowups?.(d.message_id, d.followups); else if (event === 'error') {
      finished = true;
      h.onError?.(d.detail, d.message);
    }
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        dispatch(buf.slice(0, i));
        buf = buf.slice(i + 2);
      }
    }
    if (buf.trim()) dispatch(buf);
  } catch {
    if (signal?.aborted) return;
  }
  if (!finished && !signal?.aborted) h.onError?.('The connection closed before the answer finished.');
}

// ---- Endpoints ----

export const endpoints = {
  authConfig: () => api<AuthConfig>('/auth/config'),
  signup: (b: { name: string; email: string; password: string }) => api<Me>('/auth/signup', { method: 'POST', body: b }),
  login: (b: { email: string; password: string }) => api<Me>('/auth/login', { method: 'POST', body: b }),
  logout: () => api<void>('/auth/logout', { method: 'POST' }),
  me: () => api<Me>('/me'),
  patchMe: (b: Partial<Pick<Me, 'name' | 'email' | 'theme' | 'default_kb_id'>>) => api<Me>('/me', { method: 'PATCH', body: b }),
  changePassword: (b: { current: string; new: string }) => api<void>('/me/password', { method: 'POST', body: b }),
  sessions: () => api<SessionInfo[]>('/me/sessions'),
  revokeSession: (id: string) => api<void>(`/me/sessions/${id}`, { method: 'DELETE' }),
  revokeOtherSessions: () => api<void>('/me/sessions?others=true', { method: 'DELETE' }),
  deleteMe: () => api<void>('/me', { method: 'DELETE' }),
  kbs: () => api<Kb[]>('/kbs'),
  createKb: (b: { name: string; description?: string; runtime: 'local' | 'cloud' }) =>
    api<Kb>('/kbs', { method: 'POST', body: b }),
  patchKb: (id: string, b: Partial<Pick<Kb, 'name' | 'description' | 'runtime'>>) =>
    api<Kb>(`/kbs/${id}`, { method: 'PATCH', body: b }),
  deleteKb: (id: string) => api<void>(`/kbs/${id}`, { method: 'DELETE' }),
  documents: (kbId: string) => api<Doc[]>(`/kbs/${kbId}/documents`),
  deleteDocument: (id: string) => api<void>(`/documents/${id}`, { method: 'DELETE' }),
  retryDocument: (id: string) => api<Doc>(`/documents/${id}/retry`, { method: 'POST' }),
  chats: () => api<ChatSummary[]>('/chats'),
  createChat: (kb_id: string) => api<ChatSummary>('/chats', { method: 'POST', body: { kb_id } }),
  chat: (id: string) => api<ChatDetail>(`/chats/${id}`),
  deleteChat: (id: string) => api<void>(`/chats/${id}`, { method: 'DELETE' }),
  connections: () => api<Connection[]>('/connections'),
  addConnection: (b: { api_base: string; api_key: string }) =>
    api<Connection>('/connections', { method: 'POST', body: b }),
  setConnectionModel: (id: string, selected_model: string) =>
    api<Connection>(`/connections/${id}`, { method: 'PATCH', body: { selected_model } }),
  refreshConnection: (id: string) => api<Connection>(`/connections/${id}/refresh`, { method: 'POST' }),
  removeConnection: (id: string) => api<void>(`/connections/${id}`, { method: 'DELETE' }),
};
