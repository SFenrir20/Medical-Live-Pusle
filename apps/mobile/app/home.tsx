import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { Link, Redirect } from 'expo-router';
import { Button, Card, ErrorText, Footer, Screen, s } from '../src/components/ui';
import { useSession } from '../src/features/auth/session';
import { accounts } from '../src/features/accounts';
import { getProfile, Profile } from '../src/services/api';
export default function Home() {
 const { ready, signedIn, logout, getToken, name } = useSession();
 const [profile, setProfile] = useState<Profile | null>(null);
 const [error, setError] = useState('');
 const [attempt, setAttempt] = useState(0);
 useEffect(() => {
   if (!ready || !signedIn) return;
   let active = true;
   getToken().then(getProfile).then(value => { if (active) setProfile(value); })
     .catch(() => { if (active) setError('No se pudieron cargar tus permisos. Inténtalo otra vez.'); });
   return () => { active = false; };
 }, [ready, signedIn, getToken, attempt]);
 if (!ready) return <Screen><ActivityIndicator /></Screen>;
 if (!signedIn) return <Redirect href="/" />;
 return <Screen><View style={s.row}><Text style={s.heading}>LivePulse</Text><Pressable accessibilityRole="button" onPress={() => void logout().catch(() => setError('No se pudo cerrar la sesión.'))}><Text style={s.link}>Cerrar sesión</Text></Pressable></View>
 <Text style={s.title}>Hola, {name}</Text>
 <ErrorText message={error} />{error && <Button title="REINTENTAR" onPress={() => { setError(''); setProfile(null); setAttempt(a => a + 1); }} />}
 {!profile && !error && <ActivityIndicator accessibilityLabel="Cargando permisos" />}
 {profile?.status === 'pending' && <Card><Text style={s.heading}>Acceso pendiente de aprobación</Text><Text style={s.subtitle}>Tu cuenta está registrada. El administrador debe asignarte una cuenta de TikTok para trabajar.</Text><Button title="ACTUALIZAR ESTADO" onPress={() => { setError(''); setProfile(null); setAttempt(a => a + 1); }} /></Card>}
 {profile?.status === 'approved' && <><Card><Text style={s.heading}>Tus cuentas de TikTok</Text>{accounts.filter(a => profile.accounts.includes(a.id)).map(a => <Text key={a.id} style={s.subtitle}>{a.handle}</Text>)}</Card><Card><Text style={s.heading}>Jornadas</Text><Text style={s.subtitle}>El registro de turnos y el monitoreo todavía están en desarrollo. No se ha registrado ninguna entrada.</Text><Link href="/history" style={s.link}>Ver historial</Link></Card></>}
 <Footer /></Screen>;
}
