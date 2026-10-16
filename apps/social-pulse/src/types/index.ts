/** Business roles. Assigned in Clerk (Public metadata); the API verifies them in the session. */
export type Role = "agente_ventas" | "gerente" | "jefe_marketing" | "supervisor" | "admin";
export type ScreenName = "agent" | "marketing";

export interface User {
  id: string;
  name: string;
  email: string;
  /** null = Clerk has not assigned a role: no access. */
  role: Role | null;
  screens: ScreenName[];
  permissions: string[];
  /** Why there is no access (shown to the person). */
  reason: string | null;
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** Set when the session is valid but the profile/role could not be loaded. */
  error: string | null;
}

export interface AuthContextType extends AuthState {
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}
