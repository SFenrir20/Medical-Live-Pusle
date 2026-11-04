import apiClient from "@/services/api";

export type PresenceState = {
  /** Light: online = green, paused = amber, offline = red. */
  state: "online" | "paused" | "offline";
  status: "available" | "paused";
  /** True while new contacts are being sent to this person. */
  receives: boolean;
  auto_assignment: boolean;
  pending: number;
  heartbeat_seconds: number;
  session_seconds?: number;
  active_seconds?: number;
  idle_since?: string | null;
  reconnect_required?: boolean;
};

export type TeamPresence = {
  id: string;
  name: string;
  state: "online" | "paused" | "offline";
  light: "green" | "amber" | "red";
  receives: boolean;
  last_seen_at: string | null;
  last_assigned_at: string | null;
  pending: number;
  worked: number;
  today: { connected_seconds: number; active_seconds: number; sessions: number };
  week: { connected_seconds: number; active_seconds: number; sessions: number };
};

export type TeamPresenceResponse = {
  items: TeamPresence[];
  pool_waiting: number;
  auto_assignment: boolean;
  online: number;
};

export async function sendHeartbeat(
  visible: boolean,
  status?: "available" | "paused" | "offline",
): Promise<PresenceState> {
  const { data } = await apiClient.post<PresenceState>("/presence/heartbeat", {
    visible,
    ...(status ? { status } : {}),
  });
  return data;
}

export async function fetchTeamPresence(): Promise<TeamPresenceResponse> {
  const { data } = await apiClient.get<TeamPresenceResponse>("/presence/team");
  return data;
}
