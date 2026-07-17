import { apiRequest } from "./client";

export type UserSummary = {
  id: number;
  username: string;
  full_name: string;
  role: "admin" | "user" | string;
  is_active: boolean;
  must_change_password: boolean;
  department_id?: number | null;
  position_id?: number | null;
  admin_scope_department_id?: number | null;
  admin_scope_department_name?: string | null;
  is_super_admin: boolean;
};

export type LoginResponse = {
  user: UserSummary;
  redirect_to: string;
};

export function login(username: string, password: string) {
  return apiRequest<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export function logout() {
  return apiRequest<{ message: string }>("/api/auth/logout", {
    method: "POST"
  });
}

export function getCurrentUser() {
  return apiRequest<UserSummary>("/api/auth/me");
}

export function changePassword(currentPassword: string, newPassword: string) {
  return apiRequest<{ message: string }>("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
  });
}
