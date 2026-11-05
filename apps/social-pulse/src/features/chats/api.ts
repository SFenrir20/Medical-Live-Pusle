import apiClient from "@/services/api";

/** WhatsApp transport (/whatsapp) and CRM (/crm) of the omnichannel inbox. The server decides who
 *  can see and change what; the screens only hide what a role could not do anyway. */

export type Stage = "new" | "contacted" | "qualified" | "discarded";
export type Consent = "unknown" | "granted" | "revoked";

export type ConversationItem = {
  id: number;
  phone: string;
  name: string | null;
  registry_id: number | null;
  advisor_id: string | null;
  advisor_name: string | null;
  is_mine: boolean;
  stage: Stage;
  result: string | null;
  tags: string[];
  archived: boolean;
  unread: number;
  last_message_at: string | null;
  last: {
    body: string;
    direction: "in" | "out";
    status: string;
    at: string | null;
    kind?: MediaKind | null;
    seconds?: number | null;
    name?: string | null;
  } | null;
  /** The last message is from the person and nobody has answered yet. */
  waiting?: boolean;
  consent: Consent;
  opted_out: boolean;
  origin: "tiktok_live" | "whatsapp";
  lives: number;
};

export type MediaKind = "image" | "voice" | "audio" | "video" | "document" | "sticker";
export type Counts = {
  all: number;
  mine: number;
  unread: number;
  waiting: number;
  unassigned: number;
  archived: number;
};
export type Scope = keyof Counts;

export type Note = { id: number; body: string; author_id: string; author_name: string; at: string };
export type Scheduled = {
  id: number;
  body: string;
  send_at: string;
  status: "pending" | "queued" | "cancelled";
  detail: string | null;
  author_name: string;
};
export type CrmDetail = ConversationItem & {
  notes: Note[];
  scheduled: Scheduled[];
  consent_note: string | null;
  consent_at: string | null;
  can_edit: boolean;
};

export type Message = {
  has_image?: boolean;
  media?: {
    kind: MediaKind;
    seconds: number | null;
    name: string | null;
    size: number | null;
  } | null;
  /** An old attachment that could not be recovered from WhatsApp. */
  media_unavailable?: boolean;
  id: number;
  direction: "in" | "out";
  author_kind: string;
  author_id: string | null;
  author_name?: string | null;
  body: string;
  status: string;
  error: string | null;
  at: string;
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
};
export type Appearance = {
  live_id: string;
  title: string | null;
  account_id: string;
  tiktoker_id: string | null;
  captured_at: string;
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  next_inbound_at: string | null;
  seconds_to_send: number | null;
  source: string | null;
};
export type Thread = {
  id: number;
  advisor_id: string | null;
  messages: Message[];
  has_more: boolean;
  lives: Appearance[];
};
export type WaStatus = {
  state: string;
  phone?: string | null;
  qr?: string;
  detail?: string;
  unresolved?: number;
  rejected?: number;
  sync_ok?: boolean;
  sync_at?: string;
  connected_at?: string | null;
  retry_at?: string | null;
  reconnect_attempt?: number;
  pending_events?: number;
  recovery_reason?: string | null;
};

export type QuickReply = {
  id: number;
  title: string;
  shortcut: string;
  body: string;
  active: boolean;
};
export type Summary = {
  contacts: number;
  ready_for_whatsapp: number;
  conversations: number;
  campaigns: number | null;
  automations: number | null;
};
export type ContactRow = ConversationItem & {
  id: number | null;
  conversation_id: number | null;
  message: string | null;
};
export type TeamMember = { id: string; name: string; role: string };
export type LiveLead = {
  id: number;
  user: string | null;
  message: string | null;
  phone: string | null;
  enteredAt: string;
  statusCode: Stage;
  isMine: boolean;
};

const get = async <T>(url: string, params?: object, signal?: AbortSignal) =>
  (await apiClient.get<T>(url, { params, signal })).data;
const call = async <T>(method: "post" | "put" | "patch" | "delete", url: string, data?: object) =>
  (await apiClient.request<T>({ method, url, data })).data;

export const chatApi = {
  status: (signal?: AbortSignal) => get<WaStatus>("/whatsapp/status", undefined, signal),
  connect: () => call<WaStatus>("post", "/whatsapp/connect"),
  openPhone: (phone: string) => call<{ id: number }>("post", "/whatsapp/conversations", { phone }),
  claim: (id: number) => call("post", `/whatsapp/conversations/${id}/claim`),
  seen: (id: number) => call("post", `/whatsapp/conversations/${id}/seen`),
  thread: (id: number, before: number | null, signal?: AbortSignal) =>
    get<Thread>(`/whatsapp/conversations/${id}`, before ? { before } : undefined, signal),
  send: (id: number, request_id: string, text: string) =>
    call<Message>("post", `/whatsapp/conversations/${id}/messages`, { request_id, text }),

  /** The file of a message (image, voice note, audio, video, document, sticker). */
  media: async (id: number) =>
    (
      await apiClient.get<Blob>(`/whatsapp/messages/${id}/media`, {
        responseType: "blob",
        timeout: 60000,
      })
    ).data,
  sendImage: async (id: number, request_id: string, text: string, file: File) => {
    const data = new FormData();
    data.append("request_id", request_id);
    data.append("text", text);
    data.append("file", file);
    return (
      await apiClient.post<Message>(`/whatsapp/conversations/${id}/images`, data, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 30000,
      })
    ).data;
  },

  conversations: (scope: Scope, q: string, offset: number, signal?: AbortSignal) =>
    get<{ items: ConversationItem[]; has_more: boolean; counts: Counts }>(
      "/crm/conversations",
      {
        scope,
        q,
        offset,
      },
      signal,
    ),
  detail: (id: number, signal?: AbortSignal) =>
    get<CrmDetail>(`/crm/conversations/${id}`, undefined, signal),
  patch: (
    id: number,
    body: { stage?: Stage; result?: string; tags?: string[]; archived?: boolean },
  ) => call<CrmDetail>("patch", `/crm/conversations/${id}`, body),
  markUnread: (id: number) => call<CrmDetail>("post", `/crm/conversations/${id}/unread`),
  assign: (id: number, advisor_id: string | null) =>
    call<CrmDetail>("post", `/crm/conversations/${id}/assign`, { advisor_id }),
  addNote: (id: number, body: string) =>
    call<CrmDetail>("post", `/crm/conversations/${id}/notes`, { body }),
  deleteNote: (id: number) => call<CrmDetail>("delete", `/crm/notes/${id}`),
  schedule: (id: number, text: string, send_at: string) =>
    call<CrmDetail>("post", `/crm/conversations/${id}/scheduled`, { text, send_at }),
  cancelScheduled: (id: number) => call<CrmDetail>("delete", `/crm/scheduled/${id}`),
  setConsent: (id: number, status: "granted" | "revoked", note?: string) =>
    call<CrmDetail>("put", `/crm/conversations/${id}/consent`, { status, note }),

  quickReplies: (all = false) =>
    get<{ items: QuickReply[] }>("/crm/quick-replies", all ? { all: true } : undefined).then(
      (r) => r.items,
    ),
  createReply: (body: Omit<QuickReply, "id">) =>
    call<QuickReply>("post", "/crm/quick-replies", body),
  updateReply: (id: number, body: Omit<QuickReply, "id">) =>
    call<QuickReply>("put", `/crm/quick-replies/${id}`, body),
  deleteReply: (id: number) => call<void>("delete", `/crm/quick-replies/${id}`),

  summary: () => get<Summary>("/crm/summary"),
  contacts: (q: string, stage: Stage | "", offset: number) =>
    get<{ items: ContactRow[]; has_more: boolean }>("/crm/contacts", {
      q,
      offset,
      ...(stage ? { stage } : {}),
    }),
  team: () => get<{ items: TeamMember[] }>("/team").then((r) => r.items),
  liveLeads: () =>
    get<{ items: LiveLead[] }>("/inbox", {
      phone_only: true,
      limit: 15,
      exclude_discarded: true,
    }).then((r) => r.items),
};

export function problem(
  error: unknown,
  fallback = "No se pudo completar la acción. Puedes reintentar.",
): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string };
    if (d.message) return d.message;
  }
  return fallback;
}
