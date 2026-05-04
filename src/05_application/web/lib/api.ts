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

export async function streamMessage(
  message: string,
  sessionId: string,
  onToken: (token: string) => void,
  onDone: () => void
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  if (!res.body) {
    throw new Error("No response body for stream");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE is delimited by \n\n
    const parts = buffer.split("\n\n");
    // The last element may be a partial chunk — keep it in the buffer
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const data = line.slice("data:".length).trimStart();
      if (data === "[DONE]") {
        onDone();
        return;
      }
      // Unescape newlines that were escaped before sending
      const token = data.replace(/\\n/g, "\n");
      onToken(token);
    }
  }

  // Stream ended without [DONE] — still call onDone
  onDone();
}
