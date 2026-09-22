import { useState } from 'react';
import { Text } from 'react-native';
import { Link } from 'expo-router';
import { Brand, Button, Card, ErrorText, Field, Footer, Screen, s } from '../src/components/ui';
export default function ForgotPassword() {
 const [email, setEmail] = useState(''); const [error, setError] = useState(''); const [done, setDone] = useState(false);
 function submit() {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) { setError('Ingresa un correo electrónico válido.'); return; }
  setError(''); setDone(true);
 }
 return <Screen><Brand /><Card><Text style={s.heading}>{done ? 'Vista previa de recuperación' : 'Recuperar contraseña'}</Text>
 <Text style={s.subtitle}>{done ? 'No se ha enviado ningún correo. La recuperación estará disponible cuando conectemos el servicio de autenticación.' : 'Ingresa tu correo para probar esta pantalla de recuperación.'}</Text>
 {!done && <><Field label="Correo electrónico" placeholder="andrea@livepulse.com" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" /><ErrorText message={error} /><Button title="PROBAR RECUPERACIÓN" onPress={submit} /></>}
 </Card><Link href="/" style={[s.link, { textAlign: 'center' }]}>Volver al inicio de sesión</Link><Footer /></Screen>;
}
