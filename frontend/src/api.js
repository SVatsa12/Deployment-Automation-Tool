/**
 * Backend API client. In dev, Vite proxies /api to the FastAPI server.
 * For production, set VITE_API_URL (e.g. https://api.example.com).
 */
const API_PREFIX = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

function url(path) {
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${API_PREFIX}${p}`;
}

async function request(path, options = {}) {
  const res = await fetch(url(path), {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail =
      typeof data === 'object' && data !== null && 'detail' in data
        ? data.detail
        : data;
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
          : res.statusText;
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return data;
}

/** Lightweight connectivity check (uses existing API). */
export function pingBackend() {
  return request('/api/workflows/runs?limit=1');
}

export function createWorkflow(body) {
  return request('/api/workflows', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function listWorkflowRuns(params = {}) {
  const q = new URLSearchParams();
  if (params.status) q.set('status', params.status);
  if (params.limit != null) q.set('limit', String(params.limit));
  const qs = q.toString();
  return request(`/api/workflows/runs${qs ? `?${qs}` : ''}`);
}

export function getWorkflowRun(runId) {
  return request(`/api/workflows/runs/${runId}`);
}

export function getWorkflowSteps(runId) {
  return request(`/api/workflows/runs/${runId}/steps`);
}

export function approveWorkflowRun(runId, body) {
  return request(`/api/workflows/runs/${runId}/approve`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function resumeWorkflowRun(runId) {
  return request(`/api/workflows/runs/${runId}/resume`, {
    method: 'POST',
  });
}

export function analyzeGithubRepo(githubUrl) {
  return request('/api/analyze', {
    method: 'POST',
    body: JSON.stringify({ github_url: githubUrl }),
  });
}

export function deployToPlatform(body) {
  return request('/api/deploy', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function deleteWorkflowRun(runId) {
  return request(`/api/workflows/runs/${runId}`, {
    method: 'DELETE',
  });
}
