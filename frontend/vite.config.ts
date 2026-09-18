import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
//
// The backend (FastAPI/uvicorn) runs on http://localhost:8000 in dev
// (plan Appendix B.1). We proxy /api, /auth, /admin_login, /ws, and
// /prompter under the Vite dev server's own origin so the browser never
// needs CORS and cookies set by the backend are same-site. In production
// the built SPA is served by the same origin as the backend (Traefik
// IngressRoute per Appendix A.9), so no proxy/base-URL config is needed
// there either — VITE_API_BASE_URL only ever needs to be set for a dev
// server pointed at a non-default backend port/host.
const backendTarget = process.env.VITE_API_BASE_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: backendTarget, changeOrigin: true },
      '/healthz': { target: backendTarget, changeOrigin: true },
      '/readyz': { target: backendTarget, changeOrigin: true },
      '/auth': { target: backendTarget, changeOrigin: true },
      // GET /admin_login is intentionally NOT proxied: the backend serves
      // its own plain-HTML fallback page at that path (backend/routers/auth.py),
      // but this SPA has its own React route at /admin_login (pages/AdminLogin.tsx)
      // that should render instead when a browser navigates there directly.
      // Only the POST (the actual credential submission) needs to reach the
      // backend, so `bypass` skips the proxy for anything else and lets
      // Vite fall through to the SPA's index.html/client-side routing.
      '/admin_login': {
        target: backendTarget,
        changeOrigin: true,
        bypass: (req) => (req.method === 'POST' ? undefined : req.url),
      },
      '/prompter': { target: backendTarget, changeOrigin: true },
      '/overlay': { target: backendTarget, changeOrigin: true },
      '/ws': { target: backendTarget, changeOrigin: true, ws: true },
    },
  },
})
