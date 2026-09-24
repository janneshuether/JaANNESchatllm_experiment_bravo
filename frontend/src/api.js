const API_BASE = window.location.origin;

async function sendMessageStream({ message, history, sessionId, onDelta, onTitle, signal, token }) {
  const headers = { "Content-Type": "application/json" };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, history, session_id: sessionId }),
    signal,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail || "Erro ao enviar mensagem para o servidor.";
    throw new Error(detail);
  }

  if (!response.body) {
    throw new Error("Streaming nao suportado no ambiente atual.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const rawEvent of events) {
      const line = rawEvent
        .split("\n")
        .find((part) => part.startsWith("data:"));
      if (!line) continue;

      const payloadText = line.slice(5).trim();
      if (!payloadText) continue;

      let payload;
      try {
        payload = JSON.parse(payloadText);
      } catch {
        continue;
      }

      if (payload.error) {
        throw new Error(payload.error);
      }

      if (payload.delta && onDelta) {
        onDelta(payload.delta);
      }

      if (payload.session_title && onTitle) {
        onTitle(payload.session_title);
      }
    }
  }
}

const authApi = {
  async register({ email, password }) {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "Erro ao registrar usuario.");
    }
    return data;
  },

  async login({ email, password }) {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "Erro ao realizar login.");
    }
    return data;
  },

  async logout(token) {
    if (!token) return;
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    }).catch(() => {});
  },

  async getMe(token) {
    if (!token) return null;
    const res = await fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return await res.json();
  },
};

const sessionApi = {
  async getSessions(token) {
    const headers = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/api/sessions`, { headers });
    if (!res.ok) return [];
    return await res.json();
  },

  async createSession(title, token) {
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const body = title ? JSON.stringify({ title }) : null;
    const res = await fetch(`${API_BASE}/api/sessions`, {
      method: "POST",
      headers,
      body,
    });
    if (!res.ok) throw new Error("Erro ao criar nova sessao.");
    return await res.json();
  },

  async getSessionMessages(sessionId, token) {
    if (!sessionId) return [];
    const headers = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/messages`, { headers });
    if (!res.ok) return [];
    return await res.json();
  },

  async deleteSession(sessionId, token) {
    if (!sessionId) return;
    const headers = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: "DELETE",
      headers,
    });
    if (!res.ok) throw new Error("Erro ao excluir sessao.");
    return await res.json();
  },
};
