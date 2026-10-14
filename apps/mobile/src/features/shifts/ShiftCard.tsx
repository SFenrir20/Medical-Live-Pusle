import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Text } from 'react-native';
import { Link, useFocusEffect } from 'expo-router';
import { getRandomBytes } from 'expo-crypto';
import { Button, Card, ErrorText, s } from '../../components/ui';
import { ApiError, checkIn, checkOut, getActiveShift, Shift } from '../../services/api';
import { shiftTime } from './format';

type Action = { kind: 'in' | 'out'; key: string; expected: string | null };
export function ShiftCard({ accountId, userId, getToken }: {
 accountId: string; userId: string; getToken: () => Promise<string | null>;
}) {
 const [active, setActive] = useState<Shift | null>(null);
 const [loading, setLoading] = useState(true);
 const [loaded, setLoaded] = useState(false);
 const [busy, setBusy] = useState(false);
 const [error, setError] = useState('');
 const [actionError, setActionError] = useState('');
 const [notice, setNotice] = useState('');
 const [confirm, setConfirm] = useState<'in' | 'out' | null>(null);
 const [retry, setRetry] = useState(false);
 const pending = useRef<Action | null>(null);
 const inFlight = useRef(false);
 const generation = useRef(0);
 const mounted = useRef(false);
 const observedId = useRef<string | null>(null);
 const readInFlight = useRef<number | null>(null);
 const load = useCallback(async () => {
   if (inFlight.current || pending.current || readInFlight.current !== null) return;
   const version = ++generation.current;
   readInFlight.current = version;
   setLoading(true);
   try {
     const shift = await getActiveShift(accountId, await getToken());
     if (!mounted.current || version !== generation.current) return;
     if ((shift?.id ?? null) !== observedId.current) setConfirm(null);
     observedId.current = shift?.id ?? null;
     setActive(shift); setLoaded(true); setError('');
   } catch (err) {
     if (mounted.current && version === generation.current) {
       setError(err instanceof Error ? err.message : 'No se pudo cargar el turno.');
     }
   } finally {
     if (readInFlight.current === version) readInFlight.current = null;
     if (mounted.current && version === generation.current) setLoading(false);
   }
 }, [accountId, getToken]);
 useFocusEffect(useCallback(() => {
   mounted.current = true;
   void load();
   const timer = setInterval(() => { if (!inFlight.current) void load(); }, 30000);
   const subscription = AppState.addEventListener('change', state => {
     if (state === 'active') void load();
   });
   return () => { mounted.current = false; generation.current++; readInFlight.current = null; clearInterval(timer); subscription.remove(); };
 }, [load]));
 async function mark(kind: 'in' | 'out') {
   if (inFlight.current) return;
   inFlight.current = true; generation.current++; readInFlight.current = null;
   setBusy(true); setActionError(''); setNotice('');
   try {
     // getRandomValues also works on the HTTP LAN used for server testing.
     const action = pending.current ?? { kind,
       key: Array.from(getRandomBytes(16), byte => byte.toString(16).padStart(2, '0')).join(''),
       expected: active?.id ?? null };
     pending.current = action;
     const token = await getToken();
     const saved = action.kind === 'in'
       ? await checkIn(accountId, token, action.key, action.expected)
       : await checkOut(accountId, action.expected!, token, action.key);
     pending.current = null;
     setRetry(false); setConfirm(null);
     setNotice(`${action.kind === 'in' ? 'Entrada' : 'Salida'} registrada: ${shiftTime(action.kind === 'in' ? saved.started_at : saved.ended_at!)}`);
   } catch (err) {
     const definite = err instanceof ApiError && err.status >= 400 && err.status < 500;
     if (definite) pending.current = null;
     setRetry(!!pending.current); setConfirm(null);
     setActionError(err instanceof Error ? err.message : 'No se pudo confirmar la marcación.');
   } finally {
     inFlight.current = false;
     setBusy(false);
     if (mounted.current) {
       // Re-read current state: an idempotent response may describe a turn already relieved.
       if (!pending.current) void load();
     }
   }
 }
 const mine = active?.user_id === userId;
 return <Card>
   <Text style={s.heading}>Mi jornada</Text>
   <Text style={s.subtitle}>Horarios en hora de Lima. La marcación es independiente del LIVE de TikTok.</Text>
   {!loaded && loading ? <ActivityIndicator accessibilityLabel="Consultando jornada" /> : loaded && <>
     {active ? <>
       <Text style={s.heading}>{mine ? 'Tu turno está abierto' : 'Esta cuenta tiene un turno abierto'}</Text>
       <Text style={s.subtitle}>Entrada: {shiftTime(active.started_at)}</Text>
       <Text style={s.subtitle}>{mine ? 'Cerrar sesión o la aplicación no marca tu salida.' : 'Al confirmar el relevo se cerrará el turno anterior y se registrará tu entrada a la misma hora.'}</Text>
     </> : <Text style={s.subtitle}>No hay un turno abierto en esta cuenta.</Text>}
   </>}
   <ErrorText message={error} />
   <ErrorText message={actionError} />
   {!!notice && <Text accessibilityRole="alert" style={s.notice}>{notice}</Text>}
   {retry ? <>
     <Text style={s.subtitle}>No se confirmó la respuesta. Reintenta la misma marcación para evitar duplicados.</Text>
     <Button title="REINTENTAR MARCACIÓN" busy={busy} onPress={() => { void mark(pending.current!.kind); }} />
   </> : loaded && !error && <>
     {confirm ? <>
       <Text style={s.subtitle}>{confirm === 'out' ? '¿Confirmas que terminaste tu jornada?' : '¿Confirmas que vas a reemplazar el turno abierto de esta cuenta?'}</Text>
       <Button title={confirm === 'out' ? 'CONFIRMAR SALIDA' : 'CONFIRMAR RELEVO'} busy={busy} onPress={() => { void mark(confirm); }} />
       {!busy && <Button title="CANCELAR" onPress={() => setConfirm(null)} />}
     </> : <Button title={mine ? 'MARCAR SALIDA' : active ? 'RELEVAR Y MARCAR ENTRADA' : 'MARCAR ENTRADA'} busy={busy}
       onPress={() => { if (mine) setConfirm('out'); else if (active) setConfirm('in'); else void mark('in'); }} />}
   </>}
   {!retry && !busy && (!loading || loaded) && <Button title="ACTUALIZAR ESTADO" disabled={loading} onPress={() => { void load(); }} />}
   <Link href="/history" style={s.link}>Ver historial</Link>
 </Card>;
}
