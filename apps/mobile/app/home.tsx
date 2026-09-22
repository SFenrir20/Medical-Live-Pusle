import { useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { Link, Redirect } from 'expo-router';
import { Button, Card, ErrorText, Footer, Screen, s } from '../src/components/ui';
import { useSession } from '../src/features/auth/session';
import { accounts } from '../src/features/accounts';
import { theme } from '../src/theme';
export default function Home() {
 const { ready, signedIn, logout } = useSession();
 const [account, setAccount] = useState<string>('medical');
 const [notice, setNotice] = useState('');
 if (!ready) return <Screen><ActivityIndicator /></Screen>;
 if (!signedIn) return <Redirect href="/" />;
 return <Screen><View style={[s.row, { marginBottom: 30 }]}><Text style={[s.heading, { color: theme.colors.primary }]}>LivePulse</Text><Pressable accessibilityRole="button" onPress={() => { void logout().catch(() => setNotice('No se pudo cerrar la sesión. Inténtalo otra vez.')); }}><Text style={s.link}>Cerrar sesión</Text></Pressable></View>
 <Text style={s.title}>Hola, Andrea 👋</Text><Text style={[s.subtitle, { marginBottom: 20 }]}>Tu jornada de hoy</Text>
 <Text style={s.notice}>Modo demostración · El estado del LIVE y las marcaciones todavía no están conectados.</Text>
 <Card><Text style={s.label}>CUENTA DE TIKTOK</Text>{accounts.map(item => <Pressable key={item.id} accessibilityRole="radio" accessibilityLabel={item.handle} accessibilityState={{ checked: account === item.id }} onPress={() => { setAccount(item.id); setNotice(''); }} style={{ padding: 14, marginTop: 8, borderRadius: 16, backgroundColor: account === item.id ? theme.colors.pale : theme.colors.background }}><Text style={{ color: theme.colors.ink }}>{account === item.id ? '●' : '○'} {item.handle}</Text></Pressable>)}</Card>
 <Card><Text style={s.label}>ESTADO DE JORNADA</Text><Text style={s.heading}>Sin datos de jornada real</Text><Text style={s.subtitle}>Cuenta seleccionada: {accounts.find(a => a.id === account)?.handle}</Text>
 <Button title="MARCAR INICIO" onPress={() => setNotice('Esta es una vista de demostración. No se ha registrado una entrada; falta conectar los turnos con el servidor.')} /><ErrorText message={notice} /></Card>
 <Card><Text style={s.label}>ÚLTIMA ACTIVIDAD</Text><Text style={s.subtitle}>El historial estará disponible al conectar tus turnos.</Text><Link href="/history" style={s.link}>Ver historial</Link></Card><Footer /></Screen>;
}
