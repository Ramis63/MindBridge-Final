const SESSION_KEY = 'mindbridge_session';
const TOKEN_KEY = 'mindbridge_token';

const DEFAULT_SETTINGS = {
  theme: 'light',
  anonymousSharing: false,
  onboarded: false,
  goals: [],
  reminderTime: 'evening'
};

function logsCacheKey(email) {
  const suffix = email ? email.replace(/[@.]/g, '_') : 'anonymous';
  return `mindbridge_logs_${suffix}`;
}

function settingsCacheKey(email) {
  const suffix = email ? email.replace(/[@.]/g, '_') : 'anonymous';
  return `mindbridge_settings_${suffix}`;
}

export function getCurrentUser() {
  try {
    const session = localStorage.getItem(SESSION_KEY);
    const user = session ? JSON.parse(session) : null;
    // Legacy sessions from before JWT — force re-login
    if (user && !localStorage.getItem(TOKEN_KEY)) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return user;
  } catch (e) {
    return null;
  }
}

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getLogsKey() {
  const user = getCurrentUser();
  return logsCacheKey(user?.email);
}

function getSettingsKey() {
  const user = getCurrentUser();
  return settingsCacheKey(user?.email);
}

async function apiFetch(url, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };

  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    if (response.status === 401 && token) {
      logout();
    }
    throw new Error(errData.error || `HTTP error! status: ${response.status}`);
  }
  return await response.json();
}

function persistSession(user, token) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  }
}

export async function signup(firstName, lastName, email, password) {
  const data = await apiFetch('/api/create-profile', {
    method: 'POST',
    body: JSON.stringify({ firstName, lastName, email, password })
  });

  if (data && data.user && data.token) {
    persistSession(data.user, data.token);
    return data.user;
  }
  throw new Error('Registration failed. Empty response.');
}

export async function login(email, password) {
  const data = await apiFetch('/api/session', {
    method: 'POST',
    body: JSON.stringify({ email, password })
  });

  if (data && data.user && data.token) {
    persistSession(data.user, data.token);
    return data.user;
  }
  throw new Error('Login failed. Empty response.');
}

export function logout() {
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(TOKEN_KEY);
}

export async function getLogs() {
  const user = getCurrentUser();
  const cacheKey = logsCacheKey(user?.email);
  try {
    const logs = await apiFetch('/api/logs');
    localStorage.setItem(cacheKey, JSON.stringify(logs));
    return logs;
  } catch (error) {
    console.warn('Backend unavailable — using local cache.', error);
    const localData = localStorage.getItem(cacheKey);
    if (!localData) return [];
    return JSON.parse(localData).sort((a, b) => new Date(b.date) - new Date(a.date));
  }
}

export async function getFhirBundle() {
  return apiFetch('/api/fhir/Bundle');
}

export async function getSettings() {
  const user = getCurrentUser();
  const cacheKey = settingsCacheKey(user?.email);
  try {
    const settings = await apiFetch('/api/settings');
    localStorage.setItem(cacheKey, JSON.stringify(settings));
    return settings;
  } catch (error) {
    console.warn('Backend settings unavailable — using local cache.', error);
    const localData = localStorage.getItem(cacheKey);
    return localData ? { ...DEFAULT_SETTINGS, ...JSON.parse(localData) } : DEFAULT_SETTINGS;
  }
}

export async function saveSettings(settings) {
  const cacheKey = getSettingsKey();
  localStorage.setItem(cacheKey, JSON.stringify(settings));
  try {
    await apiFetch('/api/settings', {
      method: 'POST',
      body: JSON.stringify(settings)
    });
  } catch (error) {
    console.warn('Failed to sync settings to server.', error);
  }
}

export async function upsertLog(entry) {
  const user = getCurrentUser();
  const localLogsKey = logsCacheKey(user?.email);
  const localData = localStorage.getItem(localLogsKey);
  const logs = localData ? JSON.parse(localData) : [];
  const index = logs.findIndex(log => log.date === entry.date);

  if (index !== -1) {
    logs[index] = { ...logs[index], ...entry };
  } else {
    logs.push(entry);
  }

  const sorted = logs.sort((a, b) => new Date(b.date) - new Date(a.date));
  localStorage.setItem(localLogsKey, JSON.stringify(sorted));

  // Sync to server in background — don't block the UI
  apiFetch('/api/logs', {
    method: 'POST',
    body: JSON.stringify(entry)
  }).catch((error) => {
    console.warn('Failed to sync log to server. Retained locally.', error);
  });

  return sorted;
}

/** Real-time SSE stream — charts update when a new check-in is saved. */
export function subscribeToRealtime(onEvent) {
  const token = getAuthToken();
  if (!token) return () => {};

  const controller = new AbortController();
  let closed = false;

  (async () => {
    try {
      const response = await fetch('/api/events', {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal
      });
      if (!response.ok || !response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (!closed) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';
        for (const part of parts) {
          const line = part.split('\n').find(l => l.startsWith('data: '));
          if (line) {
            try {
              onEvent(JSON.parse(line.slice(6)));
            } catch (_) { /* ignore malformed events */ }
          }
        }
      }
    } catch (error) {
      if (!closed && error.name !== 'AbortError') {
        console.warn('Realtime stream disconnected.', error);
      }
    }
  })();

  return () => {
    closed = true;
    controller.abort();
  };
}
