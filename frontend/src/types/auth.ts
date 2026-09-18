/**
 * Auth type definitions for OILTRACE.
 */

export type UserRole = "ADMIN" | "ANALYST" | "OPERATOR" | "VIEWER";

export interface AuthUser {
  id: number;
  email: string;
  employee_id: string | null;
  full_name: string;
  role: UserRole;
  department: string | null;
  last_login_at: string | null;
}

export interface LoginRequest {
  identifier: string; // email or employee_id
  password: string;
}

export interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAuth: () => Promise<void>;
}
