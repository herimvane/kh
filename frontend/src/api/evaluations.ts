import { apiRequest, downloadApiFile } from "./client";

export type Evaluation = {
  id: number;
  name: string;
  year: number;
  sequence: number;
  is_open: boolean;
  tasks_generated: boolean;
  archived: boolean;
  total_tasks: number;
  submitted_tasks: number;
  pending_reopens: number;
  scope_key: string;
  owner_department_id?: number | null;
  owner_department_name: string;
  created_by_id?: number | null;
  created_by_name?: string | null;
};

export type MyEvaluation = {
  id: number;
  name: string;
  year: number;
  sequence: number;
  owner_department_name: string;
  is_open: boolean;
  archived: boolean;
  task_count: number;
  completed_count: number;
  submitted: boolean;
  status: "pending" | "submitted" | "history";
  submitted_at?: string | null;
  created_at?: string | null;
};

export type MySubmission = {
  evaluation: Evaluation;
  submitted_at?: string | null;
  task_count: number;
  items: Array<{ id: number; target_name: string; task_type: "person" | "department"; option_name: string }>;
};

export type DashboardSummary = {
  user_total: number;
  department_total: number;
  evaluation_total: number;
  current_year_total: number;
  active_total: number;
  completed_total: number;
  total_tasks: number;
  submitted_tasks: number;
  latest: Evaluation[];
};

export type EvaluationAction = {
  message: string;
  evaluation?: Evaluation | null;
};

export type EvaluationTask = {
  id: number;
  task_type: string;
  target_id?: number | null;
  target_name: string;
  department_name: string;
  position_name: string;
  submitted: boolean;
  limit_key_rule: number | "all";
};

export type EvaluationTaskGroup = {
  type: "person" | "department";
  title: string;
  limit_text: string;
  options: { id: number; name: string }[];
  tasks: EvaluationTask[];
};

export type AppEvaluation = {
  evaluation: Evaluation | null;
  task_groups: EvaluationTaskGroup[];
  submitted: boolean;
  reopened: boolean;
  current_choices: Record<string, number>;
  limit_map: Record<string, number>;
};

export type EvaluationConfig = {
  evaluation: Evaluation;
  positions: { id: number; name: string; sort_order: number }[];
  departments: { id: number; name: string; parent_id?: number | null; display_name: string; depth: number }[];
  score_options: { id: number; name: string; value: number }[];
  person_option_ids: number[];
  department_option_ids: number[];
  person_rules: Array<Record<string, any>>;
  department_rules: Array<Record<string, any>>;
  person_limits: Array<Record<string, any>>;
  department_limits: Array<Record<string, any>>;
  share_rules: Array<Record<string, any>>;
  manual_scores: Array<Record<string, any>>;
};

export type EvaluationScorePerson = {
  id?: number;
  user_id?: number;
  username?: string;
  full_name: string;
  department_name: string;
  position_name: string;
  final_score: number;
};

export type EvaluationScoreDepartment = {
  id?: number;
  department_id?: number;
  department_name: string;
  final_score: number;
};

export type EvaluationScoreDetail = {
  id?: number;
  reviewer_name: string;
  target_name: string;
  task_type: string;
  option_name: string;
  score_value: number;
  weight: number;
  weighted_score: number;
  rule_label?: string;
};

export type ReviewSubmissionDetailResponse = {
  reviewer: {
    id: number;
    full_name: string;
    department_name: string;
    position_name: string;
  };
  items: Array<{
    id: number;
    target_name: string;
    task_type: "person" | "department";
    option_name: string;
    score_value: number;
    weight: number;
    weighted_score: number;
    created_at: string;
  }>;
  pagination: { total: number; page: number; page_size: number; pages: number };
};

export type EvaluationStatsResponse = {
  evaluation: Evaluation;
  people: EvaluationScorePerson[];
  people_pagination?: { page: number; total_pages: number; total: number; page_size: number };
  departments: EvaluationScoreDepartment[];
  details: EvaluationScoreDetail[];
  details_pagination?: { page: number; total_pages: number; total: number; page_size: number };
  snapshots?: Array<{ id: number; snapshot_type: string; title: string; payload: Array<Record<string, unknown>> }>;
  stats?: { total_tasks: number; submitted_tasks: number };
};

export const evaluationsApi = {
  list: () => apiRequest<Evaluation[]>("/api/evaluations"),
  config: (id: number) => apiRequest<EvaluationConfig>(`/api/evaluations/${id}/config`),
  create: (payload: { year: number; sequence?: number; name?: string; owner_department_id?: number | null }) =>
    apiRequest<Evaluation>("/api/evaluations", { method: "POST", body: JSON.stringify(payload) }),
  copyPreview: (id: number) => apiRequest<{
    missing: Array<{ kind: string; source_id: number; name: string }>;
    candidates: Record<string, Array<{ value: number; label: string }>>;
  }>(`/api/evaluations/${id}/copy-preview`),
  copy: (id: number, payload: { year: number; name?: string }) =>
    apiRequest<{ evaluation: Evaluation; message: string; copied_count: number; skipped_count: number; skipped: string[] }>(`/api/evaluations/${id}/copy`, { method: "POST", body: JSON.stringify(payload) }),
  delete: (id: number, adminPassword = "") =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}?admin_password=${encodeURIComponent(adminPassword)}`, { method: "DELETE" }),
  generateTasks: (id: number, confirm = false) =>
    apiRequest<EvaluationAction>(`/api/evaluations/${id}/generate-tasks?confirm=${confirm}`, { method: "POST" }),
  clearTasks: (id: number, confirm = false) =>
    apiRequest<EvaluationAction>(`/api/evaluations/${id}/clear-tasks?confirm=${confirm}`, { method: "POST" }),
  toggleOpen: (id: number) =>
    apiRequest<EvaluationAction>(`/api/evaluations/${id}/toggle-open`, { method: "POST" }),
  archive: (id: number, confirm = false) =>
    apiRequest<EvaluationAction>(`/api/evaluations/${id}/archive?confirm=${confirm}`, { method: "POST" }),
  savePersonOptions: (id: number, optionIds: number[]) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/person-options`, { method: "PUT", body: JSON.stringify(optionIds) }),
  saveDepartmentOptions: (id: number, optionIds: number[]) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/department-options`, { method: "PUT", body: JSON.stringify(optionIds) }),
  savePersonLimit: (id: number, payload: Record<string, unknown>) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/person-limits`, { method: "POST", body: JSON.stringify(payload) }),
  deletePersonLimit: (id: number, limitId: number) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/person-limits/${limitId}`, { method: "DELETE" }),
  saveDepartmentLimit: (id: number, payload: Record<string, unknown>) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/department-limits`, { method: "POST", body: JSON.stringify(payload) }),
  deleteDepartmentLimit: (id: number, limitId: number) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/department-limits/${limitId}`, { method: "DELETE" }),
  createPersonRule: (id: number, payload: Record<string, unknown>) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/person-rules`, { method: "POST", body: JSON.stringify(payload) }),
  updatePersonRule: (id: number, ruleId: number, payload: Record<string, unknown>) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/person-rules/${ruleId}`, { method: "PUT", body: JSON.stringify(payload) }),
  deletePersonRule: (id: number, ruleId: number) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/person-rules/${ruleId}`, { method: "DELETE" }),
  createDepartmentRule: (id: number, payload: Record<string, unknown>) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/department-rules`, { method: "POST", body: JSON.stringify(payload) }),
  updateDepartmentRule: (id: number, ruleId: number, payload: Record<string, unknown>) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/department-rules/${ruleId}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteDepartmentRule: (id: number, ruleId: number) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/department-rules/${ruleId}`, { method: "DELETE" }),
  saveShareRule: (id: number, payload: Record<string, unknown>) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/share-rules`, { method: "POST", body: JSON.stringify(payload) }),
  deleteShareRule: (id: number, ruleId: number) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/share-rules/${ruleId}`, { method: "DELETE" }),
  saveManualScore: (id: number, payload: Record<string, unknown>) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/manual-department-scores`, { method: "POST", body: JSON.stringify(payload) }),
  deleteManualScore: (id: number, scoreId: number) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/manual-department-scores/${scoreId}`, { method: "DELETE" }),
  liveStats: (id: number, peoplePage = 1) => apiRequest<EvaluationStatsResponse>(`/api/evaluations/${id}/live-stats?people_page=${peoplePage}`),
  reviewSubmissions: (id: number, page = 1) => apiRequest<any>(`/api/evaluations/${id}/review-submissions?page=${page}`),
  reviewSubmissionDetails: (id: number, reviewerId: number, password: string, page = 1) =>
    apiRequest<ReviewSubmissionDetailResponse>(`/api/evaluations/${id}/review-submissions/${reviewerId}/details?page=${page}`, {
      method: "POST",
      body: JSON.stringify({ password })
    }),
  reopenSubmission: (id: number, reviewerId: number, reason = "") =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/review-submissions/${reviewerId}/reopen`, { method: "POST", body: JSON.stringify({ reason }) }),
  cancelSubmission: (id: number, reviewerId: number) =>
    apiRequest<{ message: string }>(`/api/evaluations/${id}/review-submissions/${reviewerId}/cancel`, { method: "POST" }),
  details: (id: number, peoplePage = 1) => apiRequest<EvaluationStatsResponse>(`/api/evaluations/${id}/details?people_page=${peoplePage}`),
  exportPersonScores: (id: number, evaluationName: string) => downloadApiFile(`/api/evaluations/${id}/exports/person-scores`, `${evaluationName}-人员得分.xlsx`),
  exportDepartmentScores: (id: number, evaluationName: string) => downloadApiFile(`/api/evaluations/${id}/exports/department-scores`, `${evaluationName}-部门得分.xlsx`),
  audit: () => apiRequest<any>("/api/evaluations/audit"),
  dashboard: () => apiRequest<DashboardSummary>("/api/dashboard/summary"),
  myEvaluations: () => apiRequest<{ items: MyEvaluation[] }>("/api/app/evaluations"),
  appEvaluation: (evaluationId: number) => apiRequest<AppEvaluation>(`/api/app/evaluations/${evaluationId}`),
  appSubmission: (evaluationId: number) => apiRequest<MySubmission>(`/api/app/evaluations/${evaluationId}/submission`),
  submitAppEvaluation: (evaluationId: number, choices: Record<number, number>) =>
    apiRequest<{ message: string }>(`/api/app/evaluations/${evaluationId}/submit`, {
      method: "POST",
      body: JSON.stringify({ choices })
    })
};
