// Thin fetch wrappers for the RagRats API.
// All requests set credentials: 'include' so the httpOnly cookie is sent automatically.

const BASE = "/api";

async function handleResponse(res: Response): Promise<unknown> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function login(username: string, password: string): Promise<{ username: string }> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return handleResponse(res) as Promise<{ username: string }>;
}

export async function logout(): Promise<void> {
  await fetch(`${BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function createSession(): Promise<string> {
  const res = await fetch(`${BASE}/chat/sessions`, {
    method: "POST",
    credentials: "include",
  });
  const data = (await handleResponse(res)) as { session_id: string };
  return data.session_id;
}

export async function sendMessage(message: string, sessionId: string): Promise<string> {
  const res = await fetch(`${BASE}/chat/message`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  const data = (await handleResponse(res)) as { answer: string };
  return data.answer;
}
