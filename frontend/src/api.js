/**
 * IntentFlow — API Client
 * Handles all API calls with JWT auth, error handling, and base URL detection.
 */

const API_BASE = import.meta.env.VITE_API_URL || '';

function getToken() {
  return localStorage.getItem('intentflow_token');
}

function setToken(token) {
  localStorage.setItem('intentflow_token', token);
}

function setUser(user) {
  localStorage.setItem('intentflow_user', JSON.stringify(user));
}

function getUser() {
  const raw = localStorage.getItem('intentflow_user');
  return raw ? JSON.parse(raw) : null;
}

function clearAuth() {
  localStorage.removeItem('intentflow_token');
  localStorage.removeItem('intentflow_user');
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = { ...options.headers };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const resp = await fetch(url, { ...options, headers });

  if (resp.status === 401) {
    clearAuth();
    window.location.href = '/';
    throw new Error('Session expired');
  }

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }

  return resp.json();
}

// ── Auth ────────────────────────────────────────────────────────────────────

export async function login(email, password) {
  const data = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  setToken(data.access_token);
  setUser(data.user);
  return data;
}

export async function register(email, name, password) {
  const data = await request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, name, password }),
  });
  setToken(data.access_token);
  setUser(data.user);
  return data;
}

export async function getMe() {
  return request('/auth/me');
}

export { getToken, getUser, clearAuth, setToken, setUser };

// ── Tickets ──────────────────────────────────────────────────────────────────

export async function createTicket(query, sessionId = null, fromVoice = false) {
  return request('/tickets', {
    method: 'POST',
    body: JSON.stringify({
      query,
      session_id: sessionId,
      from_voice: fromVoice,
    }),
  });
}

export async function listTickets(status = null, limit = 50) {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  params.set('limit', limit.toString());
  return request(`/tickets?${params}`);
}

export async function getTicket(ticketId) {
  return request(`/tickets/${ticketId}`);
}

// ── Voice ────────────────────────────────────────────────────────────────────

export async function transcribeAudio(audioBlob) {
  const form = new FormData();
  form.append('file', audioBlob, 'recording.webm');
  return request('/voice/transcribe', { method: 'POST', body: form });
}

export async function voiceSubmit(audioBlob, sessionId = null) {
  const form = new FormData();
  form.append('file', audioBlob, 'recording.webm');
  if (sessionId) form.append('session_id', sessionId);
  return request('/voice/submit', { method: 'POST', body: form });
}

// ── Metrics ──────────────────────────────────────────────────────────────────

export async function getOverview() {
  return request('/metrics/overview');
}

export async function getByIntent() {
  return request('/metrics/by-intent');
}

export async function getByPriority() {
  return request('/metrics/by-priority');
}

export async function getByMode() {
  return request('/metrics/by-mode');
}

export async function getSLAMetrics() {
  return request('/metrics/sla');
}

export async function getTimeline(days = 30) {
  return request(`/metrics/timeline?days=${days}`);
}

export async function getRecentTickets(limit = 20, status = null) {
  const params = new URLSearchParams();
  params.set('limit', limit.toString());
  if (status) params.set('status', status);
  return request(`/metrics/recent-tickets?${params}`);
}

// ── Admin ────────────────────────────────────────────────────────────────────

export async function getUsers() {
  return request('/admin/users');
}

export async function updateUserRole(userId, role) {
  return request(`/admin/users/${userId}/role`, {
    method: 'PUT',
    body: JSON.stringify({ role }),
  });
}

export async function getSLAConfig() {
  return request('/admin/sla-config');
}
