import { apiRequest } from "./client";

export type Department = {
  id: number;
  name: string;
  parent_id?: number | null;
  parent_name?: string | null;
  sort_order: number;
};

export type DepartmentChoice = Department & {
  depth: number;
  display_name: string;
  has_children: boolean;
};

export type Position = {
  id: number;
  name: string;
  sort_order: number;
};

export type UserRow = {
  id: number;
  username: string;
  full_name: string;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  department_id?: number | null;
  position_id?: number | null;
  department_name?: string | null;
  position_name?: string | null;
  admin_scope_department_id?: number | null;
  admin_scope_department_name?: string | null;
  is_super_admin: boolean;
};

export type ScoreOption = {
  id: number;
  name: string;
  value: number;
};

export type ReviewerUser = {
  id: number;
  name: string;
  department_name?: string | null;
};

export type PagedUsers = {
  items: UserRow[];
  pagination: {
    page: number;
    total_pages: number;
    total: number;
    page_size: number;
  };
};

export const masterDataApi = {
  departments: () => apiRequest<Department[]>("/api/departments"),
  departmentChoices: () => apiRequest<DepartmentChoice[]>("/api/departments/choices"),
  createDepartment: (payload: Partial<Department>) =>
    apiRequest<Department>("/api/departments", { method: "POST", body: JSON.stringify(payload) }),
  updateDepartment: (id: number, payload: Partial<Department>) =>
    apiRequest<Department>(`/api/departments/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteDepartment: (id: number) =>
    apiRequest<{ message: string }>(`/api/departments/${id}`, { method: "DELETE" }),

  positions: () => apiRequest<Position[]>("/api/positions"),
  reviewerUsers: (positionId: number) => apiRequest<ReviewerUser[]>(`/api/positions/${positionId}/reviewer-users`),
  createPosition: (payload: Partial<Position>) =>
    apiRequest<Position>("/api/positions", { method: "POST", body: JSON.stringify(payload) }),
  updatePosition: (id: number, payload: Partial<Position>) =>
    apiRequest<Position>(`/api/positions/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deletePosition: (id: number) =>
    apiRequest<{ message: string }>(`/api/positions/${id}`, { method: "DELETE" }),

  users: (q = "", page = 1, departmentId?: number | null) => apiRequest<PagedUsers>(`/api/users?q=${encodeURIComponent(q)}&page=${page}${departmentId != null ? `&department_id=${departmentId}` : ""}`),
  createUser: (payload: Partial<UserRow> & { password?: string }) =>
    apiRequest<UserRow>("/api/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: Partial<UserRow> & { password?: string }) =>
    apiRequest<UserRow>(`/api/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteUser: (id: number) =>
    apiRequest<{ message: string }>(`/api/users/${id}`, { method: "DELETE" }),

  scoreOptions: () => apiRequest<ScoreOption[]>("/api/score-options"),
  createScoreOption: (payload: Partial<ScoreOption>) =>
    apiRequest<ScoreOption>("/api/score-options", { method: "POST", body: JSON.stringify(payload) }),
  updateScoreOption: (id: number, payload: Partial<ScoreOption>) =>
    apiRequest<ScoreOption>(`/api/score-options/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteScoreOption: (id: number) =>
    apiRequest<{ message: string }>(`/api/score-options/${id}`, { method: "DELETE" })
};
