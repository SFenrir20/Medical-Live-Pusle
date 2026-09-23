import { useAuth, useClerk, useUser } from '@clerk/expo';
export function useSession() {
 const { isLoaded, isSignedIn, getToken } = useAuth();
 const { signOut } = useClerk();
 const { user } = useUser();
 return { ready: isLoaded, signedIn: !!isSignedIn, getToken,
   name: user?.firstName || user?.primaryEmailAddress?.emailAddress || 'bienvenida',
   logout: () => signOut() };
}
