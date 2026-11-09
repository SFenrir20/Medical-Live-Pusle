import apiClient from "@/services/api";
import type { WidgetConfig, MessagePreset } from "./studio.types";

/** Everything under /api/automation and /api/chat. Writes need the admin role (the server
 *  decides; the screens only hide what the person could not do anyway). */

export type ChannelPolicy = {
  bots_enabled: boolean;
  broadcasts_enabled: boolean;
  test_only: boolean;
  test_numbers: string[];
  bot_max_per_hour: number;
  broadcast_max_per_day: number;
  min_delay_s: number;
  window_hours: number | null;
};

export type Channel = {
  id: string;
  kind: "simulator" | "whatsapp_mirror" | "whatsapp_cloud";
  name: string;
  status: "active" | "disabled";
  policy: ChannelPolicy;
  defaults: ChannelPolicy;
  risky_automation: boolean;
  bulk_safe: boolean;
};

export type CatalogEntry = { label: string; help: string };
export type Overview = {
  channels: Channel[];
  flows: { enabled: number; disabled: number };
  ai: { enabled: boolean; provider: string; has_key: boolean };
  broadcasts_active: number;
  catalog: Record<string, CatalogEntry>;
  providers: string[];
  suggested_models: Record<string, string>;
  can_manage: boolean;
};

export type GraphNode = {
  id: string;
  type: string;
  config: Record<string, unknown>;
  pos?: { x: number; y: number };
};
export type GraphEdge = { from: string; to: string; when?: "yes" | "no" };
export type FlowGraph = { nodes: GraphNode[]; edges: GraphEdge[] };

export type Flow = {
  id: number;
  name: string;
  description: string | null;
  channel_id: string;
  enabled: boolean;
  version: number;
  valid: boolean;
  updated_at: string | null;
  graph?: FlowGraph;
  errors?: string[];
  warnings?: string[];
};

export type RunStep = { node_id: string; type: string; outcome: string; at: string | null };
export type TestResult = {
  id: number;
  status: string;
  reason: string | null;
  steps: RunStep[];
  messages: { body: string; status: string; error: string | null }[];
};

export type AiConfig = {
  enabled: boolean;
  provider: string;
  model: string;
  base_url: string;
  has_key: boolean;
  key_hint: string | null;
  name: string;
  clinic_name: string;
  instructions: string;
  knowledge_only: boolean;
  handoff_keywords: string[];
  handoff_message: string;
  max_replies: number;
  daily_message_cap: number;
};

export type KnowledgeDoc = { id: number; title: string; body: string; active: boolean };
export type AiAnswer = { text: string | null; handoff: boolean; reason: string };

export type Broadcast = {
  id: number;
  name: string;
  channel_id: string;
  body: string;
  audience: Record<string, unknown>;
  status: "draft" | "scheduled" | "sending" | "paused" | "done" | "cancelled";
  pause_reason: string | null;
  total: number;
  sent: number;
  failed: number;
  skipped: number;
  created_at: string | null;
  recipients_by_status?: Record<string, number>;
  recipients?: { phone: string; name: string | null; status: string; error: string | null }[];
};

export type ChatMessage = {
  id: number;
  direction: "in" | "out";
  author_kind: "contact" | "agent" | "bot" | "system";
  body: string;
  status: string;
  error: string | null;
  at: string | null;
};
export type Conversation = {
  id: number;
  channel_id: string;
  phone: string;
  name: string | null;
  tags: string[];
  bot_active: boolean;
  last: ChatMessage | null;
};

const get = async <T>(url: string, params?: object) =>
  (await apiClient.get<T>(url, { params })).data;
const send = async <T>(method: "post" | "put" | "patch" | "delete", url: string, body?: object) =>
  (await apiClient.request<T>({ method, url, data: body })).data;

export const api = {
  widget: () => get<WidgetConfig>("/automation/studio/widget"),
  saveWidget: (body: WidgetConfig) => send<WidgetConfig>("put", "/automation/studio/widget", body),
  presets: () => get<{ items: MessagePreset[] }>("/automation/studio/messages"),
  savePresets: (items: MessagePreset[]) =>
    send<{ items: MessagePreset[] }>("put", "/automation/studio/messages", {
      items: items.map(({ key, text, enabled, delay_minutes }) => ({
        key,
        text,
        enabled,
        delay_minutes,
      })),
    }),
  overview: () => get<Overview>("/automation/overview"),
  createChannel: (body: { id: string; kind: Channel["kind"]; name: string }) =>
    send<Channel>("post", "/automation/channels", body),
  patchChannel: (
    id: string,
    body: { status?: string; policy?: Partial<ChannelPolicy>; acknowledge_risk?: boolean },
  ) => send<Channel>("patch", `/automation/channels/${id}`, body),

  flows: () => get<{ items: Flow[] }>("/automation/flows").then((r) => r.items),
  flow: (id: number) => get<Flow>(`/automation/flows/${id}`),
  createFlow: (body: { name: string; channel_id: string; graph: FlowGraph }) =>
    send<Flow>("post", "/automation/flows", body),
  saveFlow: (
    id: number,
    body: { name: string; description?: string | null; channel_id: string; graph: FlowGraph },
  ) => send<Flow>("put", `/automation/flows/${id}`, body),
  enableFlow: (id: number) => send<Flow>("post", `/automation/flows/${id}/enable`),
  disableFlow: (id: number) => send<Flow>("post", `/automation/flows/${id}/disable`),
  deleteFlow: (id: number) => send<void>("delete", `/automation/flows/${id}`),
  testFlow: (id: number, text: string) =>
    send<TestResult>("post", `/automation/flows/${id}/test`, { text }),

  ai: () => get<AiConfig>("/automation/ai/config"),
  saveAi: (body: Partial<AiConfig> & { api_key?: string; clear_key?: boolean }) =>
    send<AiConfig>("put", "/automation/ai/config", body),
  knowledge: () => get<{ items: KnowledgeDoc[] }>("/automation/ai/knowledge").then((r) => r.items),
  addKnowledge: (body: { title: string; body: string; active?: boolean }) =>
    send<KnowledgeDoc>("post", "/automation/ai/knowledge", body),
  editKnowledge: (id: number, body: { title: string; body: string; active: boolean }) =>
    send<KnowledgeDoc>("put", `/automation/ai/knowledge/${id}`, body),
  deleteKnowledge: (id: number) => send<void>("delete", `/automation/ai/knowledge/${id}`),
  playground: (messages: { role: "user" | "assistant"; content: string }[]) =>
    send<AiAnswer>("post", "/automation/ai/playground", { messages }),
  usage: () =>
    get<{
      items: { day: string; messages: number; input_tokens: number; output_tokens: number }[];
    }>("/automation/ai/usage").then((r) => r.items),

  broadcasts: () => get<{ items: Broadcast[] }>("/automation/broadcasts").then((r) => r.items),
  broadcast: (id: number) => get<Broadcast>(`/automation/broadcasts/${id}`),
  previewAudience: (audience: object) =>
    send<{ count: number; sample: { phone: string; name: string | null }[]; capped: boolean }>(
      "post",
      "/automation/broadcasts/preview",
      { audience },
    ),
  createBroadcast: (body: { name: string; channel_id: string; body: string; audience: object }) =>
    send<Broadcast>("post", "/automation/broadcasts", body),
  testBroadcast: (id: number, phone: string) =>
    send<{ sent: boolean }>("post", `/automation/broadcasts/${id}/test`, { phone }),
  startBroadcast: (id: number, confirm_total: number) =>
    send<Broadcast>("post", `/automation/broadcasts/${id}/start`, { confirm_total }),
  broadcastAction: (id: number, action: "pause" | "resume" | "cancel") =>
    send<Broadcast>("post", `/automation/broadcasts/${id}/${action}`),

  conversations: (channel_id?: string) =>
    get<{ items: Conversation[] }>("/chat/conversations", { channel_id }).then((r) => r.items),
  messages: (id: number) =>
    get<{ conversation: Conversation; messages: ChatMessage[] }>(
      `/chat/conversations/${id}/messages`,
    ),
  simulate: (phone: string, text: string, name?: string) =>
    send<{ conversation: Conversation; messages: ChatMessage[] }>(
      "post",
      "/chat/simulator/inbound",
      { phone, text, name },
    ),
  writeAsPerson: (id: number, text: string) =>
    send<ChatMessage>("post", `/chat/conversations/${id}/messages`, { text }),
  patchConversation: (id: number, body: { bot_active?: boolean; tags?: string[] }) =>
    send<Conversation>("patch", `/chat/conversations/${id}`, body),
};

/** The message to show for a failed call: our API answers {detail: "..."} or
 *  {detail: {message, errors: [...]}}. */
export function problemText(error: unknown, fallback = "No se pudo completar la acción."): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; errors?: string[] };
    return [d.message, ...(d.errors ?? [])].filter(Boolean).join(" · ");
  }
  const status = (error as { response?: { status?: number } }).response?.status;
  if (status === 403) return "Solo un administrador puede hacer esto.";
  return fallback;
}
