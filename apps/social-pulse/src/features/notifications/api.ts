import apiClient from "@/services/api";

export type AgentReminders = {
  mine_pending: number;
  mine_over_first: number;
  mine_over_second: number;
  unclaimed_waiting: number;
  first_minutes: number;
  second_minutes: number;
  oldest_minutes: number | null;
};

export type Notifications = {
  /** Reminders about my own pending chats. null when my role has no chats to work. */
  agent: AgentReminders | null;
  /** Alerts for supervisors, marketing heads and managers only; null for agents. */
  alerts: { open: number; complaints_open: number } | null;
  count: number;
};

export type AlertKind = "same_live" | "other_live" | "other_account";
export type AlertStatus = "open" | "reviewed" | "dismissed";

export type ContactAlert = {
  id: number;
  kind: AlertKind;
  kind_label: string;
  status: AlertStatus;
  repeats: number;
  note: string | null;
  phone: string;
  tiktok_username: string | null;
  contact_status: string;
  advisor: string | null;
  contacted_at: string;
  first_captured_at: string;
  first_account: string | null;
  account: string;
  live_id: string;
  live_title: string | null;
  comment_at: string;
  last_seen_at: string;
  minutes_after_contact: number;
  reviewed_by: string | null;
  reviewed_at: string | null;
};

export type Complaint = {
  id: number;
  username: string;
  comment: string;
  created_at: string;
  live_id: string;
  live_title: string | null;
  account: string;
  contacts: {
    phone: string;
    status: string;
    advisor: string | null;
    contacted_at: string | null;
  }[];
  reviewed_by: string | null;
  reviewed_at: string | null;
};

export type Page<T> = { items: T[]; total: number; next_offset: number | null };

export async function fetchNotifications(): Promise<Notifications> {
  const { data } = await apiClient.get<Notifications>("/notifications");
  return data;
}

export async function fetchAlerts(status: AlertStatus | "all", offset = 0) {
  const { data } = await apiClient.get<Page<ContactAlert>>("/alerts", {
    params: { status, offset, limit: 50 },
  });
  return data;
}

export async function reviewAlert(id: number, status: AlertStatus, note?: string) {
  const { data } = await apiClient.patch<ContactAlert>(`/alerts/${id}`, { status, note });
  return data;
}

export async function fetchComplaints(status: "open" | "reviewed" | "all", offset = 0) {
  const { data } = await apiClient.get<Page<Complaint>>("/complaints", {
    params: { status, offset, limit: 50 },
  });
  return data;
}

export async function reviewComplaint(id: number, reviewed: boolean) {
  await apiClient.patch(`/complaints/${id}`, { reviewed });
}

export async function downloadContacts(status?: string): Promise<void> {
  const { data } = await apiClient.get<Blob>("/marketing/tiktok/contacts/export", {
    responseType: "blob",
    params: status ? { status } : {},
  });
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = "contactos.xlsx";
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
