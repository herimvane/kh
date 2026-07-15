import { apiRequest } from "./client";

export type SystemSettings = { system_name: string };

export const settingsApi = {
  get: () => apiRequest<SystemSettings>("/api/settings"),
  update: (systemName: string) => apiRequest<SystemSettings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify({ system_name: systemName })
  })
};
