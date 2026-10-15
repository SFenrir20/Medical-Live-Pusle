import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, fetchInbox, fetchTeam, LeadApi, patchLead, TeamMember } from "./api";

export type MessageStatus = "Nuevo" | "Contactado";

/** Row shown by the dashboard; built from the backend, never from local mock data. */
export type SocialMessage = {
  id: number;
  kind: "lead" | "comment";
  account: string;
  platform: "TikTok" | "Instagram";
  source: string;
  user: string;
  liveHost: string;
  message: string;
  phone?: string;
  type: "Comentario" | "Interesado" | "Paciente potencial";
  status: MessageStatus;
  owner?: string;
  ownerId?: string;
  isMine: boolean;
  enteredAt: string;
  /** Time of the FIRST contact; stays even if the status is changed later. */
  contactedAt?: string;
  contactSeconds?: number;
};

const limaTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("es-PE", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Lima",
  });

export function toMessage(item: LeadApi): SocialMessage {
  return {
    id: item.id,
    kind: item.kind,
    account: item.account,
    platform: item.platform,
    source: item.source,
    user: item.user ?? "Sin usuario",
    liveHost: item.liveHost ?? "Sin asignar",
    message: item.message ?? "Teléfono registrado sin comentario",
    phone: item.phone ?? undefined,
    type: item.type,
    status: item.statusCode === "new" ? "Nuevo" : "Contactado",
    owner: item.owner ?? undefined,
    ownerId: item.ownerId ?? undefined,
    isMine: item.isMine,
    enteredAt: limaTime(item.enteredAt),
    contactedAt: item.contactedAt ? limaTime(item.contactedAt) : undefined,
    contactSeconds: item.contactTimeSeconds ?? undefined,
  };
}

const POLL_MS = 5000;

/** Inbox + actions. Every change goes through the API, so reloading never loses it. */
export function useWorkspace(enabled = true, phoneOnly = true) {
  const [messages, setMessages] = useState<SocialMessage[]>([]);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Set<number>>(new Set());
  const [total, setTotal] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const busy = useRef(false);
  const requestId = useRef(0);
  const loadedPages = useRef(1);

  const reload = useCallback(
    async (pages = loadedPages.current) => {
      if (busy.current) return false;
      busy.current = true;
      const ticket = ++requestId.current;
      try {
        const rows: LeadApi[] = [];
        let offset: number | null = 0;
        let count = 0;
        for (let page = 0; page < pages && offset !== null; page++) {
          const inbox = await fetchInbox(phoneOnly, offset);
          if (ticket !== requestId.current) return false;
          rows.push(...inbox.items);
          offset = inbox.next_offset;
          count = inbox.total;
        }
        // Replace the loaded window on refresh: never retain contacts whose permissions
        // or assignment changed. Ignore requests from a previous filter or unmounted view.
        if (ticket !== requestId.current) return false;
        setMessages(Array.from(new Map(rows.map((row) => [row.id, row])).values()).map(toMessage));
        setTotal(count);
        setNextOffset(offset);
        loadedPages.current = pages;
        setError(null);
        return true;
      } catch (err) {
        if (ticket === requestId.current)
          setError(errorMessage(err, "No se pudo actualizar la bandeja."));
        return false;
      } finally {
        if (ticket === requestId.current) {
          busy.current = false;
          setLoading(false);
        }
      }
    },
    [phoneOnly],
  );

  useEffect(() => {
    requestId.current++;
    busy.current = false;
    loadedPages.current = 1;
    setMessages([]);
    setTotal(0);
    setNextOffset(null);
    setLoading(true);
    if (!enabled) return;
    void reload();
    let cancelled = false;
    fetchTeam()
      .then((members) => {
        if (!cancelled) setTeam(members);
      })
      .catch(() => undefined);
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void reload();
    }, POLL_MS);
    return () => {
      cancelled = true;
      requestId.current++;
      busy.current = false;
      window.clearInterval(timer);
    };
  }, [enabled, reload]);

  const loadMore = useCallback(async () => {
    if (nextOffset === null) return false;
    return reload(loadedPages.current + 1);
  }, [nextOffset, reload]);

  const run = useCallback(
    async (id: number, body: Parameters<typeof patchLead>[1]) => {
      if (id < 0) return; // a plain comment has no phone, so there is nothing to assign
      setPending((current) => new Set(current).add(id));
      try {
        const saved = toMessage(await patchLead(id, body));
        setMessages((current) => current.map((message) => (message.id === id ? saved : message)));
        setError(null);
      } catch (err) {
        setError(errorMessage(err, "No se pudo guardar el cambio."));
        await reload();
      } finally {
        setPending((current) => {
          const next = new Set(current);
          next.delete(id);
          return next;
        });
      }
    },
    [reload],
  );

  const claim = useCallback(
    (id: number) => run(id, { action: "claim", expect_unassigned: true }),
    [run],
  );
  const setStatus = useCallback(
    (id: number, status: MessageStatus, current: MessageStatus) =>
      run(id, {
        status: status === "Contactado" ? "contacted" : "new",
        expected_status: current === "Nuevo" ? "new" : undefined,
      }),
    [run],
  );

  return {
    messages,
    team,
    loading,
    error,
    pending,
    claim,
    setStatus,
    reload,
    total,
    hasMore: nextOffset !== null,
    loadMore,
  };
}
