import { useState } from 'react';
import { useHostedAuth } from '@clerk/expo/hosted-auth';
import { Text } from 'react-native';
import { Button, Card, ErrorText, s } from '../../components/ui';
export default function Access() {
 const { startHostedAuth } = useHostedAuth();
 const [busy, setBusy] = useState(false);
 const [error, setError] = useState('');
 async function open(mode: 'sign-in' | 'sign-up') {
   setBusy(true); setError('');
   try { await startHostedAuth({ mode }); }
   catch { setError('No se pudo abrir el acceso. Inténtalo otra vez.'); }
   finally { setBusy(false); }
 }
 return <Card><Text style={s.heading}>Bienvenida</Text><Text style={s.subtitle}>Accede a tu cuenta para consultar tu jornada. También puedes recuperar tu contraseña desde el formulario de acceso.</Text><Button title="INICIAR SESIÓN" busy={busy} onPress={() => void open('sign-in')} /><Button title="CREAR CUENTA" busy={busy} onPress={() => void open('sign-up')} /><ErrorText message={error} /></Card>;
}
