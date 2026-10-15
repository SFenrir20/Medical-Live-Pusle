import apiClient from "@/services/api";

/** Shapes returned by the backend (see docs/social-live-api.md). */
export type LeadApi = {
  kind: "lead" | "comment";
  id: number;
  live_id: string;
  account: string;
  platform: "TikTok";
  source: string;
  user: string | null;
  liveHost: string | null;
  liveHostId: string | null;
  message: string | null;
  phone: string | null;
  type: "Comentario" | "Interesado" | "Paciente potencial";
  status: string;
  statusCode: "new" | "contacted" | "qualified" | "discarded";
  ownerId: string | null;
  owner: string | null;
  isMine: boolean;
  enteredAt: string;
  contactedAt: string | null;
  contactTimeSeconds: number | null;
};

export type InboxResponse = {
  items: LeadApi[];
  me: string;
  total: number;
  next_offset: number | null;
};
export type TeamMember = { id: string; name: string; role: string };
export type Summary = {
  unassigned: number;
  agents: { id: string; name: string; assigned: number; pending: number; contacted: number }[];
};
export type LiveApi = {
  id: string;
  status: "scheduled" | "live" | "finished" | "cancelled";
  account: string | null;
  tiktoker: string | null;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  metrics: {
    views: number;
    /** Highest simultaneous audience sample. Not unique viewers. */
    peak_viewers: number;
    average_viewers: number | null;
    /** null = no source connected ("no disponible"). */
    unique_viewers: number | null;
    comments_count: number;
    likes_count: number;
    shares_count: number;
    new_followers: number;
    donations_count: number;
    /** What a sender reported; only meaningful when direct_messages_capture is true. */
    direct_messages_reported: number;
    direct_messages_capture: boolean;
    interested_viewers: number;
    /** Contacts whose FIRST capture was in this live. */
    phones_captured: number;
    phone_mentions: number;
    leads_per_hour: number;
  };
};

export async function fetchInbox(phoneOnly: boolean, offset = 0): Promise<InboxResponse> {
  const { data } = await apiClient.get<InboxResponse>("/inbox", {
    params: { limit: 200, offset, phone_only: phoneOnly, exclude_discarded: true },
  });
  return data;
}

export async function patchLead(
  id: number,
  body: {
    action?: "claim" | "release" | "assign";
    advisor_id?: string;
    status?: "new" | "contacted" | "qualified" | "discarded";
    expected_status?: string;
    expect_unassigned?: boolean;
  },
): Promise<LeadApi> {
  const { data } = await apiClient.patch<LeadApi>(`/leads/${id}`, body);
  return data;
}

export async function fetchSummary(): Promise<Summary> {
  const { data } = await apiClient.get<Summary>("/leads/summary");
  return data;
}

export async function fetchTeam(): Promise<TeamMember[]> {
  const { data } = await apiClient.get<{ items: TeamMember[] }>("/team");
  return data.items;
}

export async function fetchLives(status?: string, limit = 30): Promise<LiveApi[]> {
  const { data } = await apiClient.get<{ items: LiveApi[] }>("/marketing/tiktok/lives", {
    params: { limit, ...(status ? { status } : {}) },
  });
  return data.items;
}

export async function saveProfileName(name: string): Promise<void> {
  await apiClient.put("/auth/me/profile", { name });
}

export async function downloadLiveComments(liveId: string): Promise<void> {
  try {
    const { data } = await apiClient.get<Blob>(
      `/marketing/tiktok/lives/${encodeURIComponent(liveId)}/comments/export`,
      { responseType: "blob" },
    );
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `comentarios_${liveId}.xlsx`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    const response = (error as { response?: { status?: number } }).response;
    if (response?.status === 410) {
      throw new Error(
        "Los comentarios detallados de este Live ya no están disponibles. Las métricas históricas permanecen disponibles.",
      );
    }
    throw new Error("No se pudo descargar el archivo. Inténtalo otra vez.");
  }
}

export function errorMessage(error: unknown, fallback: string): string {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })
    .response;
  const detail = response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (response?.status === 403) return "Tu rol no permite esta operación.";
  if (response?.status === 409) return "Otra persona cambió este contacto. Se actualizó la lista.";
  return fallback;
}
