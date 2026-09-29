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
  connections: () => api<Connection[]>('/connections'),
  addConnection: (b: { api_base: string; api_key: string }) =>
    api<Connection>('/connections', { method: 'POST', body: b }),
  setConnectionModel: (id: string, selected_model: string) =>
    api<Connection>(`/connections/${id}`, { method: 'PATCH', body: { selected_model } }),
  refreshConnection: (id: string) => api<Connection>(`/connections/${id}/refresh`, { method: 'POST' }),
  removeConnection: (id: string) => api<void>(`/connections/${id}`, { method: 'DELETE' }),
};
