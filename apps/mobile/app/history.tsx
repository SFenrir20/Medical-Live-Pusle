import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Text } from 'react-native';
import { Link, Redirect, useFocusEffect } from 'expo-router';
import { Button, Card, ErrorText, Footer, Screen, s } from '../src/components/ui';
import { useSession } from '../src/features/auth/session';
import { accounts } from '../src/features/accounts';
import { shiftDuration, shiftTime } from '../src/features/shifts/format';
import { getShiftHistory, Shift } from '../src/services/api';
export default function History() {
 const { ready, signedIn, getToken } = useSession();
 const [items, setItems] = useState<Shift[]>([]);
 const [next, setNext] = useState<number | null>(null);
 const [busy, setBusy] = useState(false);
 const [error, setError] = useState('');
 const version = useRef(0);
 const load = useCallback(async (offset = 0) => {
   const request = ++version.current; setBusy(true); setError('');
   try {
     const page = await getShiftHistory(await getToken(), offset);
     if (request !== version.current) return;
     setItems(previous => offset ? [...previous, ...page.items.filter(item => !previous.some(p => p.id === item.id))] : page.items);
     setNext(page.next_offset);
   } catch (err) {
     if (request === version.current) setError(err instanceof Error ? err.message : 'No se pudo cargar el historial.');
   } finally { if (request === version.current) setBusy(false); }
 }, [getToken]);
 useFocusEffect(useCallback(() => {
   if (ready && signedIn) void load();
   return () => { version.current++; };
 }, [ready, signedIn, load]));
 if (!ready) return <Screen><ActivityIndicator /></Screen>;
 if (!signedIn) return <Redirect href="/" />;
 return <Screen>
   <Link href="/home" style={s.link}>← Volver a mi jornada</Link>
   <Text style={s.heading}>Historial de mis jornadas</Text>
   <Text style={s.subtitle}>Horarios en hora de Lima. Solo se muestran tus turnos.</Text>
   <ErrorText message={error} />
   <Button title="ACTUALIZAR HISTORIAL" busy={busy} onPress={() => { void load(); }} />
   {!busy && !error && items.length === 0 && <Card><Text style={s.subtitle}>Todavía no has marcado una entrada.</Text></Card>}
   {items.map(shift => <Card key={shift.id}>
     <Text style={s.heading}>{accounts.find(a => a.id === shift.account_id)?.handle ?? shift.account_id}</Text>
     <Text style={s.subtitle}>Entrada: {shiftTime(shift.started_at)}</Text>
     <Text style={s.subtitle}>Salida: {shift.ended_at ? shiftTime(shift.ended_at) : 'Turno abierto'}</Text>
     {shift.ended_at && <Text style={s.subtitle}>Duración: {shiftDuration(shift.started_at, shift.ended_at)}</Text>}
     <Text style={s.subtitle}>{shift.end_reason === 'handover' ? 'Cierre automático por relevo' : shift.end_reason === 'manual' ? 'Salida marcada por ti' : 'En curso'}</Text>
   </Card>)}
   {next !== null && <Button title="VER MÁS" busy={busy} onPress={() => { void load(next); }} />}
   <Footer />
 </Screen>;
}
