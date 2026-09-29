export type UserRole = "BIDDER" | "OFFICER";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  bidder_id: string | null;
  company_name: string | null;
  is_active: boolean;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  full_name: string;
  email: string;
  password: string;
  company_name: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface AuthLog {
  id: string;
  event_type: string;
  success: boolean;
  ip_address: string | null;
  created_at: string;
  details: Record<string, unknown> | null;
}

const TOKEN_KEY = "tender_volks_access_token";

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
}

function getErrorMessage(data: unknown, fallback: string): string {
  if (
    typeof data === "object" &&
    data !== null &&
    "detail" in data
  ) {
    const detail = (data as { detail?: unknown }).detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (
            typeof item === "object" &&
            item !== null &&
            "msg" in item
          ) {
            return String((item as { msg: unknown }).msg);
          }

          return String(item);
        })
        .join(", ");
    }
  }

  return fallback;
}

export async function login(
  payload: LoginPayload,
): Promise<AuthResponse> {
  const response = await fetch("/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      getErrorMessage(data, "Unable to sign in."),
    );
  }

  saveToken(data.access_token);
  return data;
}

export async function register(
  payload: RegisterPayload,
): Promise<AuthResponse> {
  const response = await fetch("/auth/register", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      getErrorMessage(data, "Unable to create account."),
    );
  }

  saveToken(data.access_token);
  return data;
}

export async function getCurrentUser(): Promise<AuthUser> {
  const token = getToken();

  if (!token) {
    throw new Error("No active session.");
  }

  const response = await fetch("/auth/me", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  const data = await response.json();

  if (!response.ok) {
    clearAuth();
    throw new Error(
      getErrorMessage(data, "Session expired."),
    );
  }

  return data;
}

export async function getActivity(): Promise<AuthLog[]> {
  const token = getToken();

  if (!token) {
    throw new Error("No active session.");
  }

  const response = await fetch("/auth/activity", {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      getErrorMessage(data, "Unable to load activity."),
    );
  }

  return data;
}

export async function logout(): Promise<void> {
  const token = getToken();

  if (token) {
    try {
      await fetch("/auth/logout", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
    } catch {
      // Local session is still cleared below.
    }
  }

  clearAuth();
}

export function hasSession(): boolean {
  return Boolean(getToken());
}
