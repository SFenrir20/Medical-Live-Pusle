import apiClient from "@/services/api";
import type { ConversationItem } from "@/features/chats/api";

/** Funnels (embudos) of the CRM: /api/crm/pipelines. The server decides who may move or edit. */
export type Funnel = { id: number; name: string; default: boolean };
export type FunnelStage = {
  id: number;
  name: string;
  color: string;
  description: string | null;
  position: number;
  legacy_stage: string | null;
};
export type Card = ConversationItem & { value_cents: number; entered_at: string | null };
export type Column = FunnelStage & {
  count: number;
  value_cents: number;
  cards: Card[];
  has_more: boolean;
};
export type Board = { pipeline: Funnel; stages: Column[]; total: number; value_cents: number };
export type FunnelDetail = Funnel & { stages: FunnelStage[] };
export type Template = { key: string; name: string; stages: string[] };
export type StageMetric = { stage_id: number; current: number; entered: number };
export type StageDraft = { id: number | null; name: string; color: string; description: string };

const get = async <T>(url: string, params?: object) =>
  (await apiClient.get<T>(url, { params })).data;

export const funnelApi = {
  list: () => get<{ items: Funnel[] }>("/crm/pipelines").then((r) => r.items),
  templates: () => get<{ items: Template[] }>("/crm/pipelines/templates").then((r) => r.items),
  create: async (name: string, template: string) =>
    (await apiClient.post<FunnelDetail>("/crm/pipelines", { name, template })).data,
  patch: async (id: number, body: { name?: string; archived?: boolean }) =>
    (await apiClient.patch<FunnelDetail>(`/crm/pipelines/${id}`, body)).data,
  saveStages: async (id: number, stages: StageDraft[]) =>
    (await apiClient.put<FunnelDetail>(`/crm/pipelines/${id}/stages`, { stages })).data,
  board: (id: number, q: string, mine: boolean) =>
    get<Board>(`/crm/pipelines/${id}/board`, { q, mine }),
  moreCards: (id: number, stage: number, offset: number, q: string, mine: boolean) =>
    get<{ cards: Card[]; has_more: boolean }>(`/crm/pipelines/${id}/stages/${stage}/cards`, {
      offset,
      q,
      mine,
    }),
  putCard: async (
    id: number,
    conversation: number,
    body: { stage_id?: number; value_cents?: number },
  ) =>
    (
      await apiClient.put<{
        conversation_id: number;
        stage_id: number | null;
        value_cents: number;
      }>(`/crm/pipelines/${id}/cards/${conversation}`, body)
    ).data,
  removeCard: async (id: number, conversation: number) => {
    await apiClient.delete(`/crm/pipelines/${id}/cards/${conversation}`);
  },
  metrics: (id: number) =>
    get<{ items: StageMetric[] }>(`/crm/pipelines/${id}/metrics`).then((r) => r.items),
};

export const money = (cents: number) =>
  cents ? `S/ ${(cents / 100).toLocaleString("es-PE", { maximumFractionDigits: 2 })}` : "S/ 0";
