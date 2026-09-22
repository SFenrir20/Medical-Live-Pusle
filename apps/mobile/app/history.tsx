import { ActivityIndicator, Text } from 'react-native';
import { Link, Redirect } from 'expo-router';
import { Card, Footer, Screen, s } from '../src/components/ui';
import { useSession } from '../src/features/auth/session';
export default function History() {
 const { ready, signedIn } = useSession();
 if (!ready) return <Screen><ActivityIndicator /></Screen>;
 if (!signedIn) return <Redirect href="/" />;
 return <Screen><Link href="/home" style={s.link}>← Volver a mi jornada</Link><Card><Text style={s.heading}>Historial de jornadas</Text><Text style={s.subtitle}>Todavía no hay una conexión con los registros del servidor. Aquí podrás consultar las entradas y salidas de cada cuenta.</Text></Card><Footer /></Screen>;
}
