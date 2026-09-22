import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, PropsWithChildren, useContext, useEffect, useState } from 'react';
const KEY = 'livepulse.preview-session.v1';
export const DEMO = { email: 'andrea@livepulse.com', password: '123456' };
type Session = { ready: boolean; signedIn: boolean; login: (email: string, password: string, remember: boolean) => Promise<void>; logout: () => Promise<void> };
const Context = createContext<Session | null>(null);
export function SessionProvider({ children }: PropsWithChildren) {
 const [ready, setReady] = useState(false);
 const [signedIn, setSignedIn] = useState(false);
 useEffect(() => {
  let mounted = true;
  AsyncStorage.getItem(KEY).then(value => { if (mounted) setSignedIn(value === 'demo'); })
   .catch(() => {}).finally(() => { if (mounted) setReady(true); });
  return () => { mounted = false; };
 }, []);
 async function login(email: string, password: string, remember: boolean) {
  if (email.trim().toLowerCase() !== DEMO.email || password !== DEMO.password) throw new Error('Correo o contraseña incorrectos. Usa el acceso de demostración.');
  // Store only a demo marker, never passwords or real tokens.
  if (remember) await AsyncStorage.setItem(KEY, 'demo'); else await AsyncStorage.removeItem(KEY);
  setSignedIn(true);
 }
 async function logout() { await AsyncStorage.removeItem(KEY); setSignedIn(false); }
 return <Context.Provider value={{ ready, signedIn, login, logout }}>{children}</Context.Provider>;
}
export function useSession() { const value = useContext(Context); if (!value) throw new Error('SessionProvider requerido'); return value; }
