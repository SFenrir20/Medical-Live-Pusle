import { ClerkProvider } from '@clerk/expo';
import { esES } from '@clerk/localizations';
import { tokenCache } from '@clerk/expo/token-cache';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Text } from 'react-native';
import { Brand, Card, Screen, s } from '../src/components/ui';
const key = process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY;
export default function Layout() {
 if (!key) return <Screen><Brand /><Card><Text style={s.heading}>Acceso no configurado</Text><Text style={s.subtitle}>Contacta al administrador para habilitar el acceso a LivePulse.</Text></Card></Screen>;
 return <ClerkProvider publishableKey={key} localization={esES} tokenCache={tokenCache}><StatusBar style="dark" /><Stack screenOptions={{ headerShown: false }} /></ClerkProvider>;
}
