import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type { WhoAmI } from '../types/api';

export function useWhoAmI() {
  return useQuery({
    queryKey: ['auth', 'whoami'],
    queryFn: () => apiFetch<WhoAmI>('/api/v1/auth/whoami'),
    staleTime: Infinity,
    retry: false,
  });
}

export async function adminLogin(username: string, password: string): Promise<void> {
  const form = new URLSearchParams();
  form.set('username', username);
  form.set('password', password);
  const res = await fetch('/admin_login', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form.toString(),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? 'Login failed');
  }
}

export async function logout(): Promise<void> {
  await apiFetch('/auth/logout', { method: 'POST' });
}
