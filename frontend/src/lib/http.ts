/**
 * Native `fetch` wrapper (plan Appendix B.2: no Axios). This is the ONLY
 * place raw `fetch()` is allowed to appear outside `frontend/src/api/*.ts`
 * query/mutation functions (plan §C.5 rule 7 / §C.3) — pages and components
 * must go through TanStack Query hooks instead.
 *
 * Auth is cookie-based (signed session cookie set by the backend on OIDC
 * callback or /admin_login) — `credentials: 'include'` on every request is
 * what makes subsequent API calls authenticated, per the plan's "the
 * frontend doesn't manage tokens itself" instruction.
 */

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function parseBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  body?: unknown;
  /** Send as multipart/form-data instead of JSON (video upload). */
  formData?: FormData;
  query?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, options.query);
  const init: RequestInit = {
    method: options.method ?? 'GET',
    credentials: 'include',
  };

  if (options.formData) {
    init.body = options.formData;
    // Do not set Content-Type — the browser sets the multipart boundary.
  } else if (options.body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(options.body);
  }

  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await parseBody(res);
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(res.status, detail, body);
  }
  if (res.status === 204) return undefined as T;
  return (await parseBody(res)) as T;
}
