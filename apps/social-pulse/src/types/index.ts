/** Business roles, assigned by the backend (never trusted from the browser). */
export type Role = "agente_ventas" | "gerente" | "jefe_marketing" | "supervisor" | "admin";
export type ScreenName = "agent" | "marketing";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  screens: ScreenName[];
  permissions: string[];
  canManageRoles: boolean;
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
