import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, MessageCircle, Send, RefreshCw } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import api from '@/services/api';
import { usePresence } from '@/features/presence/usePresence';
import { PresenceControl } from '@/features/presence/PresenceControl';

type Conversation = { id: number; phone: string; name: string | null; advisor_id: string | null;
  contact_status: string | null; unread: number; last_message_at: string | null };
type Message = { id: number; direction: string; author_kind: string; author_id: string | null;
  body: string; status: string; error: string | null; at: string; sent_at: string | null;
  delivered_at: string | null; read_at: string | null; author_name?: string | null };
type Appearance = { live_id: string; title: string | null; account_id: string; tiktoker_id: string | null;
  captured_at: string; sent_at: string | null; seconds_to_send: number | null; source: string | null;
  delivered_at: string | null; read_at: string | null; next_inbound_at: string | null };
type Detail = Conversation & { messages: Message[]; has_more: boolean; lives: Appearance[] };
type Status = { state: string; phone?: string | null; qr?: string; detail?: string; unresolved?: number; rejected?: number; sync_ok?: boolean; sync_at?: string };
const labels: Record<string, string> = { queued: 'En cola', sending: 'Confirmando envío', sent: 'Enviado',
  delivered: 'Entregado', read: 'Leído', received: 'Recibido', unknown: 'Envío sin confirmar', blocked: 'No enviado' };
const states: Record<string, string> = { connected: 'Conectado', connecting: 'Conectando', qr: 'Espera vinculación',
  disconnected: 'Desconectado', unavailable: 'Conector no disponible', relink_required: 'Requiere nueva vinculación',
  wrong_number: 'No se pudo identificar la cuenta o no coincide con la cuenta vinculada' };
const date = (value: string | null) => value ? new Date(value).toLocaleString('es-PE', { timeZone: 'America/Lima' }) : '—';
function errorText(error: unknown) {
  const data = error as { response?: { data?: { detail?: unknown } } };
  return typeof data.response?.data?.detail === 'string' ? data.response.data.detail : 'No se pudo completar la solicitud. Puedes reintentar.';
}

export function WhatsAppInbox() {
  const { user } = useAuth();
  const mayRead = !!user?.permissions.includes('wa:read');
  const maySend = !!user?.permissions.includes('wa:send');
  const mayManage = !!user?.permissions.includes('wa:manage');
  const { presence, failed: presenceFailed, setStatus: setPresenceStatus } = usePresence(maySend);
  const [status, setStatus] = useState<Status>({ state: 'connecting' });
  const [items, setItems] = useState<Conversation[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [phone, setPhone] = useState('');
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [before, setBefore] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<{ id: string; text: string; conversation: number } | null>(null);
  const opened = useRef(false);
  const messageList = useRef<HTMLDivElement>(null);
  const followMessages = useRef(true);
  const selectedRef = useRef(selected); selectedRef.current = selected;

  const choose = useCallback((id: number) => {
    setSelected(id); setDetail(null); setBefore(null); setDraft(''); setError('');
    request.current = null;
    followMessages.current = true;
  }, []);
  useEffect(() => {
    if (!before && followMessages.current && messageList.current)
      messageList.current.scrollTop = messageList.current.scrollHeight;
  }, [detail?.messages.length, detail?.id, before]);
  const openPhone = useCallback(async (value: string) => {
    try {
      const { data } = await api.post<Conversation>('/whatsapp/conversations', { phone: value.trim() });
      choose(data.id);
    } catch (err) { setError(errorText(err)); }
  }, [choose]);

  useEffect(() => {
    if (!mayRead || opened.current) return;
    opened.current = true;
    const initialPhone = new URLSearchParams(window.location.search).get('phone');
    if (initialPhone) { setPhone(initialPhone); void openPhone(initialPhone); }
  }, [mayRead, openPhone]);

  useEffect(() => {
    if (!mayRead) return;
    let stopped = false, timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const [list, connection] = await Promise.all([
          api.get<{ items: Conversation[]; has_more: boolean }>('/whatsapp/conversations', { params: { q: search, offset } }),
          api.get<Status>('/whatsapp/status'),
        ]);
        if (!stopped) { setItems(list.data.items); setHasMore(list.data.has_more); setStatus(connection.data); }
      } catch (err) { if (!stopped) { setError(errorText(err)); setStatus({ state: 'unavailable' }); } }
      if (!stopped) timer = setTimeout(poll, 4000);
    };
    timer = setTimeout(poll, 250);
    return () => { stopped = true; clearTimeout(timer); };
  }, [mayRead, search, offset]);

  useEffect(() => {
    if (!selected || !mayRead) return;
    let stopped = false, timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const { data } = await api.get<Detail>(`/whatsapp/conversations/${selected}`, { params: { before } });
        if (!stopped) setDetail(data);
      } catch (err) { if (!stopped) { setDetail(null); setError(errorText(err)); } }
      if (!stopped) timer = setTimeout(poll, 3000);
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [selected, before, mayRead]);

  async function connect() {
    setBusy(true); setError('');
    try { const { data } = await api.post<Status>('/whatsapp/connect'); setStatus(data); }
    catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  async function claim() {
    if (!selected) return;
    setBusy(true); setError('');
    try {
      const { data } = await api.post<Conversation>(`/whatsapp/conversations/${selected}/claim`);
      if (selectedRef.current === selected) setDetail(old => old ? { ...old, ...data } : old);
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!selected || !draft.trim() || busy) return;
    const text = draft.trim(), conversation = selected;
    if (!request.current || request.current.text !== text || request.current.conversation !== conversation)
      request.current = { id: crypto.randomUUID(), text, conversation };
    setBusy(true); setError('');
    try {
      const { data } = await api.post<Message>(`/whatsapp/conversations/${conversation}/messages`, {
        request_id: request.current.id, text,
      });
      if (selectedRef.current === conversation) {
        followMessages.current = true;
        setDetail(old => old ? { ...old, messages: [...old.messages.filter(m => m.id !== data.id), data] } : old);
        setDraft(''); setBefore(null); request.current = null;
      }
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  }
  if (!mayRead) return <main className="p-8">Tu rol no tiene acceso a WhatsApp. <a href="/">Volver</a></main>;
  const own = detail?.advisor_id === user?.id;
  return <main className="min-h-screen bg-canvas p-4 text-ink sm:p-6">
    <header className="mx-auto mb-5 flex max-w-[1600px] flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-4"><a href="/" aria-label="Volver al panel"><ArrowLeft /></a>
        <div><h1 className="text-xl font-bold">WhatsApp · Social Pulse</h1>
          <p className="text-sm text-muted">Atención y evidencia de los contactos de tus LIVE · Hora de Lima</p></div></div>
      <div className="flex items-center gap-3"><span className={status.state === 'connected' ? 'text-emerald-700' : 'text-amber-700'}>
        {states[status.state] || status.state} {status.phone}</span>
        {maySend && <PresenceControl presence={presence} failed={presenceFailed} onChange={setPresenceStatus} />}
        {mayManage && status.state !== 'connected' && <button className="primary-button" disabled={busy} onClick={connect}>Vincular / reconectar</button>}
      </div>
    </header>
    {error && <div role="alert" className="mx-auto mb-4 max-w-[1600px] rounded-xl bg-red-50 p-3 text-red-800">{error}</div>}
    {status.detail && <p className="mx-auto mb-4 max-w-[1600px] text-sm text-muted">{status.detail}</p>}
    {status.state === 'connected' && status.sync_ok === false && <p role="alert" className="mx-auto mb-4 max-w-[1600px] rounded-xl bg-amber-50 p-3 text-amber-800">WhatsApp está vinculado, pero la sincronización no está al día. Última sincronización: {date(status.sync_at || null)}. Contacta al administrador.</p>}
    {mayManage && status.qr && <section className="mx-auto mb-5 flex max-w-[1600px] flex-wrap items-center gap-5 rounded-2xl border border-line bg-white p-5">
      <img src={status.qr} width={220} height={220} alt="QR de vinculación de WhatsApp" />
      <div><h2 className="font-bold">{status.phone ? `Vincula el número ${status.phone}` : 'Vincula tu cuenta de WhatsApp'}</h2>
        <p>En tu teléfono: WhatsApp → Dispositivos vinculados → Vincular dispositivo.</p>
        {!status.phone && <p className="mt-2 text-sm text-muted">Detectaremos y guardaremos el número al escanear el QR.</p>}
        <p className="mt-2 text-sm text-muted">El QR se renueva. Solo supervisores y administradores pueden verlo.</p></div>
    </section>}
    {!!status.unresolved && <p className="mx-auto mb-4 max-w-[1600px] text-sm text-amber-800">Hay mensajes pendientes de identificar por teléfono. El conector reintentará al recibir la correspondencia de WhatsApp.</p>}
    {!!status.rejected && <p role="alert" className="mx-auto mb-4 max-w-[1600px] rounded-xl bg-amber-50 p-3 text-sm text-amber-800">Hay {status.rejected} mensajes o confirmaciones guardados pendientes de revisión por un error de datos. Contacta al administrador.</p>}
    <section className="mx-auto grid max-w-[1600px] gap-4 lg:grid-cols-[280px_minmax(0,1fr)_300px]">
      <aside className="rounded-2xl border border-line bg-white p-4">
        <h2 className="mb-3 font-bold">Conversaciones</h2>
        <input aria-label="Buscar conversación" className="mb-4 w-full rounded-lg border border-line p-2 text-sm" placeholder="Buscar teléfono o nombre"
          value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} />
        <form className="mb-4 flex gap-2" onSubmit={e => { e.preventDefault(); void openPhone(phone); }}>
          <input aria-label="Teléfono con código de país" className="min-w-0 flex-1 rounded-lg border border-line p-2 text-sm" value={phone}
            onChange={e => setPhone(e.target.value)} placeholder="+519…" pattern="\+[1-9][0-9]{7,14}" required />
          <button className="text-sm font-bold text-primary">Abrir</button>
        </form>
        <div className="max-h-[60vh] space-y-2 overflow-auto">{items.map(c => <button key={c.id} onClick={() => choose(c.id)}
          className={`w-full rounded-xl p-3 text-left ${selected === c.id ? 'bg-primary-soft' : 'hover:bg-slate-50'}`}>
          <span className="block font-semibold">{c.name || c.phone}</span><span className="block text-xs text-muted">{c.phone}</span>
          <span className="text-xs text-muted">{c.advisor_id === user?.id ? 'Mi contacto' : c.advisor_id ? 'Asignado' : 'Sin asignar'}{c.unread > 0 ? ` · ${c.unread} sin revisar` : ''}</span>
        </button>)}{!items.length && <p className="py-6 text-sm text-muted">Aún no hay conversaciones en esta vista.</p>}</div>
        <div className="mt-3 flex justify-between text-sm text-primary">
          <button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>Anterior</button>
          <button disabled={!hasMore} onClick={() => setOffset(offset + 50)}>Siguiente</button>
        </div>
      </aside>
      <section className="flex min-h-[650px] min-w-0 flex-col rounded-2xl border border-line bg-white">
        {detail ? <>
          <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line p-4">
            <div><h2 className="font-bold">{detail.name || detail.phone}</h2><p className="text-sm text-muted">{detail.phone}</p></div>
            {maySend && !detail.advisor_id && <button className="primary-button" disabled={busy} onClick={claim}>Tomar contacto</button>}
            {own && <button className="text-xs text-primary" onClick={() => void api.post(`/whatsapp/conversations/${detail.id}/seen`).catch(e => setError(errorText(e)))}>Marcar revisado aquí</button>}
          </header>
          <div ref={messageList} onScroll={e => { const el = e.currentTarget; followMessages.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }} className="flex max-h-[60vh] flex-1 flex-col gap-3 overflow-auto bg-slate-50 p-4">
            <div className="flex justify-between text-xs text-primary">
              {detail.has_more && <button onClick={() => setBefore(detail.messages[0].id)}>Mensajes anteriores</button>}
              {before && <button onClick={() => setBefore(null)}>Volver a recientes</button>}
            </div>
            {!detail.messages.length && <p className="py-12 text-center text-sm text-muted">Sin mensajes registrados. La sincronización comienza al vincular; no importa todo el historial anterior.</p>}
            {detail.messages.map(m => <article key={m.id} className={`max-w-[90%] rounded-2xl border border-line p-3 ${m.direction === 'out' ? 'self-end bg-emerald-50' : 'self-start bg-white'}`}>
              <p className="whitespace-pre-wrap break-words text-sm">{m.body}</p>
              <p className="mt-2 text-[11px] text-muted">{date(m.at)} · {labels[m.status] || m.status}</p>
              {m.direction === 'out' && <p className="text-[11px] text-muted">{m.author_kind === 'agent' ? `Asesor: ${m.author_name || m.author_id}` : 'Desde teléfono u otro dispositivo; persona no identificada'}</p>}
              {(m.sent_at || m.delivered_at || m.read_at) && <details className="mt-1 text-[11px] text-muted"><summary>Tiempos registrados</summary>
                <p>Enviado: {date(m.sent_at)}</p><p>Entrega: {date(m.delivered_at)}</p><p>Lectura: {date(m.read_at)}</p>
                <p>Las confirmaciones sin hora de origen usan la hora en que fueron observadas.</p></details>}
              {m.error && <p className="mt-2 text-xs text-amber-800">{m.error}</p>}
            </article>)}
          </div>
          <form onSubmit={send} className="border-t border-line p-4">
            <textarea aria-label="Mensaje de WhatsApp" className="w-full resize-none rounded-xl border border-line p-3 text-sm"
              value={draft} onChange={e => setDraft(e.target.value)} maxLength={4000} rows={3}
              disabled={!own || !maySend || busy} placeholder={own ? 'Escribe tu respuesta…' : 'Toma el contacto para responder'} />
            <div className="mt-2 flex items-center justify-between gap-3"><p className="text-xs text-muted">Texto por WhatsApp. Enviado, entregado y leído se registran por separado.</p>
              <button className="primary-button" disabled={busy || !own || !maySend || !draft.trim() || status.state !== 'connected' || status.sync_ok === false}>
                {busy ? <RefreshCw size={16} /> : <Send size={16} />} Enviar</button></div>
          </form>
        </> : <div className="grid flex-1 place-items-center p-8 text-center text-muted"><div><MessageCircle className="mx-auto mb-3" />Selecciona una conversación o abre el teléfono de un contacto.</div></div>}
      </section>
      <aside className="rounded-2xl border border-line bg-white p-4">
        <h2 className="font-bold">Capturas y atención</h2>
        <p className="mt-2 text-xs text-muted">El estado manual del CRM y la evidencia de WhatsApp son distintos. Una entrega no prueba que la persona respondió.</p>
        {detail && <p className="my-3 text-sm">Estado en CRM: <strong>{detail.contact_status || 'Sin registro LIVE'}</strong></p>}
        {detail?.lives.map(live => <article key={live.live_id} className="mt-3 rounded-xl border border-line p-3 text-sm">
          <h3 className="font-bold">{live.title || live.live_id}</h3><p>{live.account_id} · {live.tiktoker_id || 'Sin responsable'}</p>
          <p className="mt-2 text-xs text-muted">Captura: {date(live.captured_at)}</p>
          <p className="mt-2 text-xs">{live.seconds_to_send === null ? 'Sin envío posterior registrado' : `Primer envío posterior: ${Math.round(live.seconds_to_send / 60)} min`}</p>
          {live.sent_at && <p className="text-xs text-muted">{date(live.sent_at)} · {live.source === 'social_pulse' ? 'Social Pulse' : 'Otro dispositivo'}</p>}
          {live.sent_at && <div className="mt-2 text-xs text-muted"><p>Entregado: {date(live.delivered_at)}</p>
            <p>Leído: {date(live.read_at)}</p><p>Mensaje recibido después: {date(live.next_inbound_at)}</p></div>}
        </article>)}
        {detail && !detail.lives.length && <p className="mt-4 text-sm text-muted">Este teléfono aún no está asociado a un LIVE capturado.</p>}
      </aside>
    </section>
  </main>;
}
