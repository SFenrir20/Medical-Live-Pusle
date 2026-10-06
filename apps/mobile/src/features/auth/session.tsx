import { useAuth, useClerk, useUser } from '@clerk/expo';
import { useCallback, useLayoutEffect, useRef } from 'react';
export function useSession() {
 const { isLoaded, isSignedIn, getToken: clerkGetToken, sessionId } = useAuth();
 // Expo's Clerk wrapper creates getToken again on every render. Keep effects stable,
 // while always calling the latest implementation (tokens are never cached here).
 const auth = useRef({ getToken: clerkGetToken, sessionId });
 useLayoutEffect(() => { auth.current = { getToken: clerkGetToken, sessionId }; },
   [clerkGetToken, sessionId]);
 const getToken = useCallback(() => {
   if (auth.current.sessionId !== sessionId) return Promise.resolve(null);
   return auth.current.getToken();
 }, [sessionId]);
 const { signOut } = useClerk();
 const { user } = useUser();
 return { ready: isLoaded, signedIn: !!isSignedIn, getToken,
   name: user?.firstName || user?.primaryEmailAddress?.emailAddress || 'bienvenida',
   logout: () => signOut() };
}
