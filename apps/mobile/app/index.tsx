import { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { Link, Redirect } from 'expo-router';
import { Brand, Button, Card, ErrorText, Field, Footer, Screen, s } from '../src/components/ui';
import { DEMO, useSession } from '../src/features/auth/session';
export default function Login() {
 const session = useSession();
 const [email, setEmail] = useState('');
 const [password, setPassword] = useState('');
 const [show, setShow] = useState(false);
 const [remember, setRemember] = useState(true);
 const [error, setError] = useState('');
 const [busy, setBusy] = useState(false);
 const pending = useRef(false);
 async function submit() {
  if (pending.current) return;
  setError('');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) { setError('Ingresa un correo electrónico válido.'); return; }
  if (!password) { setError('Ingresa tu contraseña.'); return; }
  pending.current = true; setBusy(true);
  try { await session.login(email, password, remember); }
  catch (e) { setError(e instanceof Error ? e.message : 'No pudimos abrir la sesión.'); }
  finally { pending.current = false; setBusy(false); }
 }
 if (!session.ready) return <Screen><ActivityIndicator accessibilityLabel="Cargando sesión" /></Screen>;
 if (session.signedIn) return <Redirect href="/home" />;
 return <Screen><Brand /><Card><Text style={s.heading}>Bienvenida</Text><Text style={s.subtitle}>Inicia sesión para comenzar tu jornada.</Text>
 <Field label="Correo electrónico" placeholder={DEMO.email} value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" editable={!busy} />
 <Field label="Contraseña" placeholder="••••••" value={password} onChangeText={setPassword} secureTextEntry={!show} autoCapitalize="none" autoComplete="current-password" editable={!busy} onSubmitEditing={submit} />
 <Pressable accessibilityRole="button" onPress={() => setShow(!show)}><Text style={[s.link, { textAlign: 'right' }]}>{show ? 'Ocultar contraseña' : 'Mostrar contraseña'}</Text></Pressable>
 <View style={s.row}><Pressable accessibilityRole="checkbox" accessibilityState={{ checked: remember }} accessibilityLabel="Recordar sesión" onPress={() => setRemember(!remember)}><Text style={s.subtitle}>{remember ? '☑' : '☐'} Recordar sesión</Text></Pressable><Link href="/forgot-password" style={s.link}>¿Olvidaste tu contraseña?</Link></View>
 <ErrorText message={error} /><Button title="INICIAR SESIÓN" busy={busy} onPress={submit} />
 </Card><Text style={s.notice}>Modo demostración · No registra turnos reales.{'\n'}Acceso: {DEMO.email} / {DEMO.password}</Text><Footer /></Screen>;
}
