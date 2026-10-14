import { useCallback, useState } from 'react';
import { Platform, Share, Text, View } from 'react-native';
import { Link, Redirect, useFocusEffect } from 'expo-router';
import { Button, Card, ErrorText, Field, Footer, Screen, s } from '../src/components/ui';
import { useSession } from '../src/features/auth/session';
import { staffRequest } from '../src/services/api';

type Role = 'tiktoker' | 'marketing' | 'care' | 'admin';
type Live = { id: number; account_id: string; started_at: string; pending_events: number;
 metrics: { comments: number; likes: number; shares: number; interested_users: number;
   observed_followers: number; donors: number; peak_viewers: number | null; leads: number } };
type Contact = { id: string; users: string[]; phones: string[]; status: string; review_needed: boolean };
export default function Staff() {
 const { ready, signedIn, getToken } = useSession();
 const [role, setRole] = useState<Role>('tiktoker');
 const [lives, setLives] = useState<Live[]>([]);
 const [contacts, setContacts] = useState<Contact[]>([]);
 const [users, setUsers] = useState<{id: string; role: Role}[]>([]);
 const [error, setError] = useState('');
 const [notice, setNotice] = useState('');
 const [busy, setBusy] = useState(false);
 const [text, setText] = useState('');
 const [username, setUsername] = useState('');
 const [reviewNote, setReviewNote] = useState('');
 const [tab, setTab] = useState<'marketing' | 'care' | 'users'>('marketing');
 const [next, setNext] = useState<number | null>(null);
 const [offset, setOffset] = useState(0);
 const [monitor, setMonitor] = useState('');
 const load = useCallback(async () => {
   setBusy(true); setError('');
   try {
     const token = await getToken();
     const capability = await staffRequest('/v1/capabilities', token);
     setRole(capability.role);
     if (capability.role === 'care' && tab !== 'care') { setTab('care'); return; }
     if (tab === 'marketing' && ['marketing','admin'].includes(capability.role)) {
       const page = await staffRequest(`/v1/analytics/lives?offset=${offset}`, token);
       setLives(page.items); setNext(page.next_offset);
       const health = await staffRequest('/v1/monitor/status', token);
       setMonitor(health.accounts.map((a: {account_id: string; stale: boolean; status: string}) => `${a.account_id}: ${a.stale ? 'sin señal reciente' : a.status}`).join(' · ') + ` · Eventos pendientes: ${health.pending_events}${health.worker_stale ? ' · Procesador sin señal reciente' : ''}`);
     }
     if (tab === 'care' && ['care','admin'].includes(capability.role)) {
       const page = await staffRequest(`/v1/contacts?offset=${offset}`, token);
       setContacts(page.items); setNext(page.next_offset);
     }
     if (tab === 'users' && capability.role === 'admin') {
       setUsers(await staffRequest('/v1/staff/users', token)); setNext(null);
     }
   } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo cargar la sección.'); }
   finally { setBusy(false); }
 }, [getToken, tab, offset]);
 useFocusEffect(useCallback(() => { if (ready && signedIn) void load(); }, [ready, signedIn, load]));
 async function action(path: string, method: string, body?: unknown) {
   setBusy(true); setError(''); setNotice('');
   try {
     const result = await staffRequest(path, await getToken(), { method,
       headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
     if (result.csv) {
       if (Platform.OS === 'web') {
         const url = URL.createObjectURL(new Blob(['\ufeff' + result.csv], { type: 'text/csv;charset=utf-8' }));
         const a = document.createElement('a'); a.href = url; a.download = result.filename; a.click();
         setTimeout(() => URL.revokeObjectURL(url), 1000);
       } else await Share.share({ message: result.csv });
       setNotice('Archivo preparado. Importa el CSV en Leadsales; no se enviaron mensajes.');
     } else { setNotice('Cambios guardados.'); await load(); }
   } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo guardar.'); }
   finally { setBusy(false); }
 }
 async function readImage(file: File) {
   setBusy(true); setError('');
   try {
     const data = new FormData(); data.append('file', file);
     const result = await staffRequest('/v1/contacts/ocr', await getToken(), { method: 'POST', body: data });
     setText(result.text); setNotice('Revisa y corrige el teléfono antes de guardar. La lectura puede contener errores.');
   } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo leer la captura.'); }
   finally { setBusy(false); }
 }
 if (!ready) return <Screen><Text>Cargando…</Text></Screen>;
 if (!signedIn) return <Redirect href="/" />;
 function section(value: typeof tab) { setTab(value); setOffset(0); setNext(null); setNotice(''); }
 return <Screen><Link href="/home" style={s.link}>← Mi jornada</Link>
   <Text style={s.title}>Panel del equipo</Text><Text style={s.subtitle}>Tu usuario: {role}</Text>
   <ErrorText message={error} />{!!notice && <Text style={s.notice}>{notice}</Text>}
   {role === 'tiktoker' ? <Card><Text style={s.subtitle}>Tu registro permite marcar jornadas. Un administrador puede asignarte acceso de Marketing o Atención al Cliente.</Text></Card> : <>
     <View style={s.row}>
       {['marketing','admin'].includes(role) && <Button title="MARKETING" busy={busy} onPress={() => section('marketing')} />}
       {['care','admin'].includes(role) && <Button title="ATENCIÓN" busy={busy} onPress={() => section('care')} />}
       {role === 'admin' && <Button title="USUARIOS" busy={busy} onPress={() => section('users')} />}
     </View>
     <Button title="ACTUALIZAR" busy={busy} onPress={() => { void load(); }} />
     {tab === 'marketing' && ['marketing','admin'].includes(role) && <>
       <Text style={s.subtitle}>{monitor}</Text>
       <Text style={s.notice}>Métricas observadas durante la captura. Mensajes directos, espectadores únicos totales y ventas no están conectados.</Text>
       {!lives.length && <Text style={s.subtitle}>Todavía no hay LIVE registrados.</Text>}
       {lives.map(live => <Card key={live.id}><Text style={s.heading}>{live.account_id}</Text>
         <Text style={s.subtitle}>Detectado: {new Date(live.started_at).toLocaleString('es-PE', { timeZone: 'America/Lima' })}</Text>
         <Text style={s.subtitle}>Comentarios: {live.metrics.comments} · Likes: {live.metrics.likes} · Compartidos: {live.metrics.shares}</Text>
         <Text style={s.subtitle}>Interesados: {live.metrics.interested_users} · Seguidores observados: {live.metrics.observed_followers}</Text>
         <Text style={s.subtitle}>Donadores: {live.metrics.donors} · Pico observado: {live.metrics.peak_viewers ?? 'Sin muestras'} · Contactos: {live.metrics.leads}</Text>
         <Text style={s.subtitle}>Eventos pendientes: {live.pending_events}</Text>
       </Card>)}
     </>}
     {tab === 'care' && ['care','admin'].includes(role) && <>
       <Card><Text style={s.heading}>Teléfonos de comentarios o capturas</Text>
         {Platform.OS === 'web' && <input aria-label="Leer captura" type="file" accept="image/png,image/jpeg,image/webp" disabled={busy}
           onChange={e => { const file = e.target.files?.[0]; if (file) void readImage(file); e.target.value = ''; }} />}
         <Field label="Usuario TikTok (opcional)" value={username} onChangeText={setUsername} />
         <Field label="Texto revisado con teléfono" value={text} onChangeText={setText} multiline />
         <Button title="GUARDAR CONTACTO REVISADO" busy={busy} onPress={() => { void action('/v1/contacts/manual','POST',{ text, username: username || null }); }} />
       </Card>
       <Button title="DESCARGAR CSV PARA LEADSALES" busy={busy} onPress={() => { void action('/v1/contacts/export/leadsales','POST'); }} />
       <Text style={s.subtitle}>Solo se exportan contactos listos sin conflictos. La descarga no confirma su importación.</Text>
       {!contacts.length && <Text style={s.subtitle}>Sin contactos registrados.</Text>}
       {contacts.map(contact => <Card key={contact.id}>
         <Text style={s.heading}>{contact.users.join(', ') || 'Contacto manual'}</Text>
         <Text style={s.subtitle}>{contact.phones.join(' · ') || 'Sin teléfono'}</Text>
         <Text style={s.subtitle}>Estado: {contact.status}{contact.review_needed ? ' · Identidad en conflicto; requiere revisión' : ''}</Text>
         {contact.review_needed && role === 'admin' && <><Field label="Motivo de la revisión de identidad" value={reviewNote} onChangeText={setReviewNote} /><Button title="CONFIRMAR IDENTIDAD REVISADA" busy={busy} onPress={() => { void action(`/v1/contacts/${contact.id}/review`, 'POST', { note: reviewNote }); }} /></>}
         {(['ready','contacted','scheduled','closed','invalid'] as const).map((status, i) => <Button key={status}
           title={['LISTO PARA EXPORTAR','CONTACTADO','CITA AGENDADA','CERRADO','DESCARTAR'][i]} busy={busy}
           onPress={() => { void action(`/v1/contacts/${contact.id}`, 'PATCH', { status, expected_status: contact.status }); }} />)
         }
       </Card>)}
     </>}
     {tab === 'users' && role === 'admin' && users.map(user => <Card key={user.id}>
       <Text selectable style={s.heading}>{user.id}</Text><Text style={s.subtitle}>Rol: {user.role}</Text>
       {(['tiktoker','marketing','care','admin'] as Role[]).map((r, i) => <Button key={r} title={['TIKTOKER','MARKETING','ATENCIÓN AL CLIENTE','ADMINISTRADOR'][i]} busy={busy}
         onPress={() => { void action(`/v1/staff/users/${user.id}/role`, 'PUT', { role: r }); }} />)}
     </Card>)}
     {offset > 0 && <Button title="PRIMERA PÁGINA" busy={busy} onPress={() => setOffset(0)} />}
     {next !== null && <Button title="SIGUIENTE PÁGINA" busy={busy} onPress={() => setOffset(next)} />}
   </>}
   <Footer />
 </Screen>;
}
