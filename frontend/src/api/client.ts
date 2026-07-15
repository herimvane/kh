export type ApiError = {
  detail?: string;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include"
  });

  if (!response.ok) {
    let message = "请求失败，请稍后重试。";
    try {
      const payload = (await response.json()) as ApiError;
      if (payload.detail) message = payload.detail;
    } catch {
      // Keep the generic message when the server returns a non-JSON error.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export async function downloadApiFile(path: string, filename: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  if (!response.ok) {
    let message = "导出失败，请稍后重试。";
    try {
      const payload = (await response.json()) as ApiError;
      if (payload.detail) message = payload.detail;
    } catch {
      // Keep the generic message for non-JSON errors.
    }
    throw new Error(message);
  }
  const blobUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(blobUrl);
}
