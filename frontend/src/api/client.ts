// Centralized API Client Module for LAN and production access
const getBaseUrl = (): string => {
  if (import.meta.env.MODE === 'production') {
    // Relative paths ('/api/...') automatically use window.location.origin on both desktop and phone
    return '';
  }
  return (import.meta.env.VITE_API_URL as string) || '';
};

export const API_BASE_URL = getBaseUrl();

export async function apiFetch<T = any>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = endpoint.startsWith('/') ? `${API_BASE_URL}${endpoint}` : `${API_BASE_URL}/${endpoint}`;
  
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${response.statusText}`);
  }

  return response.json();
}
