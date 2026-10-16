import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useAuth as useClerkAuth, useClerk, useUser } from "@clerk/react";
import apiClient, { setTokenProvider } from "@/services/api";
import { saveProfileName } from "@/features/workspace/api";
import { AuthContextType, Role, ScreenName, User } from "@/types";

interface MeResponse {
  id: string;
  role: Role | null;
  screens: ScreenName[];
  permissions: string[];
  reason: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Identity AND role come from Clerk; /api/auth/me returns the role the server verified in the
 * session and the screens it opens.
 * Fail closed: if the role cannot be loaded the person gets no dashboard, not a default one.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn, getToken, userId } = useClerkAuth();
  const { user: clerkUser } = useUser();
  const { signOut } = useClerk();
  const [profile, setProfile] = useState<MeResponse | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const getTokenRef = useRef(getToken);
  getTokenRef.current = getToken;

  useEffect(() => {
    setTokenProvider(() => getTokenRef.current());
  }, []);

  const reload = useCallback(async () => {
    setLoadingProfile(true);
    setError(null);
    try {
      const { data } = await apiClient.get<MeResponse>("/auth/me");
      setProfile(data);
    } catch {
      setProfile(null);
      setError("No se pudo verificar tu acceso. Comprueba tu conexión e inténtalo otra vez.");
    } finally {
      setLoadingProfile(false);
    }
  }, []);

  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      setProfile(null);
      setError(null);
      return;
    }
    void reload();
  }, [isLoaded, isSignedIn, userId, reload]);

  // Supervisors and reports show people by name, so remember it server-side (best effort).
  const profileId = profile?.id;
  const clerkName = clerkUser?.fullName || clerkUser?.firstName || clerkUser?.username || "";
  useEffect(() => {
    if (profileId && clerkName) void saveProfileName(clerkName).catch(() => undefined);
  }, [profileId, clerkName]);

  const logout = useCallback(async () => {
    setProfile(null);
    await signOut();
  }, [signOut]);

  const value = useMemo<AuthContextType>(() => {
    const email = clerkUser?.primaryEmailAddress?.emailAddress ?? "";
    const name =
      clerkUser?.fullName || clerkUser?.firstName || clerkUser?.username || email || "Usuario";
    const user: User | null = profile
      ? {
          id: profile.id,
          name,
          email,
          role: profile.role,
          screens: profile.screens,
          permissions: profile.permissions,
          reason: profile.reason,
        }
      : null;
    return {
      user,
      isAuthenticated: !!user,
      isLoading: !isLoaded || (!!isSignedIn && loadingProfile && !profile),
      error: isSignedIn ? error : null,
      logout,
      reload,
    };
  }, [clerkUser, profile, isLoaded, isSignedIn, loadingProfile, error, logout, reload]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
