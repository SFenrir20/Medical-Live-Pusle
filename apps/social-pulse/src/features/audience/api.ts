import apiClient from "@/services/api";

export type AudienceSort = "diamonds" | "comments" | "likes" | "shares" | "presence" | "lives";

export type Fan = {
  /** TikTok id (without @) and the name shown on the screen. */
  user: string;
  name: string | null;
  user_key: string;
  comments: number;
  likes: number;
  shares: number;
  gifts: number;
  diamonds: number;
  follows: number;
  followed: boolean;
  /** Lives in which the person showed up (only meaningful in the accumulated view). */
  lives: number;
  /** Estimate: first to last time the person showed up in an event. */
  presence_seconds: number;
  first_seen_at: string;
  last_seen_at: string;
  /** Whether she left a phone number. The number itself is never sent. */
  left_contact: boolean;
};

export type AudienceTop = {
  scope: "live" | "period";
  live_id: string | null;
  days: number | null;
  sort: AudienceSort;
  /** People counted in the scope (items shows only the top). */
  members: number;
  items: Fan[];
  retention_days: number;
  note: string;
};

export async function fetchAudienceTop(params: {
  liveId?: string;
  days?: number;
  sort: AudienceSort;
  limit?: number;
}): Promise<AudienceTop> {
  const { data } = await apiClient.get<AudienceTop>("/audience/top", {
    params: {
      sort: params.sort,
      limit: params.limit ?? 30,
      ...(params.liveId ? { live_id: params.liveId } : { days: params.days ?? 30 }),
    },
  });
  return data;
}
