/**
 * Auth and Employee type definitions for OILTRACE.
 */

export type UserRole = "TECH_ADMIN" | "ADMIN" | "ANALYST" | "OPERATOR" | "VIEWER";
export type AccountStatus = "PENDING_ACTIVATION" | "ACTIVE" | "DEACTIVATED";

export interface AuthUser {
  id: number;
  employee_id: string;
  official_email: string;
  email: string;
  full_name: string;
  role: UserRole;
  department: string | null;
  account_status: AccountStatus;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at?: string;
}

export interface EmployeeItem {
  id: number;
  employee_id: string;
  official_email: string;
  email: string;
  full_name: string;
  role: UserRole;
  department: string | null;
  account_status: AccountStatus;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CreateEmployeePayload {
  employee_id: string;
  official_email: string;
  full_name: string;
  department?: string;
  role: UserRole;
}

export interface TokenVerificationData {
  employee_id: string;
  official_email: string;
  full_name: string;
  department?: string | null;
  role: string;
}

export interface LoginRequest {
  identifier: string; // official_email or employee_id
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
