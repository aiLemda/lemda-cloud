import type {
  AgentRunResponse,
  ChatTurn,
  Conversation,
  ConversationSummary,
  HealthResponse,
  SessionStats,
  ToolStep,
} from "./agent";

export async function checkHealth(): Promise<HealthResponse> {
  let res: Response;
  try {
    res = await fetch("/api/health");
  } catch {
    return { status: "down" };
  }
  if (!res.ok) return { status: "down" };
  return (await res.json()) as HealthResponse;
}

export async function fetchSessionStats(): Promise<SessionStats> {
  let res: Response;
  try {
    res = await fetch("/api/sessions/stats");
  } catch {
    return { live_sessions: null, max_sessions: null, live_containers: null, stale_containers: null };
  }
  if (!res.ok) {
    return { live_sessions: null, max_sessions: null, live_containers: null, stale_containers: null };
  }
  return (await res.json()) as SessionStats;
}

export async function createConversation(): Promise<Conversation | null> {
  try {
    const res = await fetch("/api/conversations", { method: "POST" });
    if (!res.ok) return null;
    return (await res.json()) as Conversation;
  } catch {
    return null;
  }
}

export async function getConversation(id: string): Promise<Conversation | null> {
  try {
    const res = await fetch(`/api/conversations/${id}`);
    if (!res.ok) return null;
    return (await res.json()) as Conversation;
  } catch {
    return null;
  }
}

export async function appendConversationMessage(
  id: string,
  role: "user" | "assistant",
  content: string,
): Promise<ChatTurn[] | null> {
  try {
    const res = await fetch(`/api/conversations/${id}/messages`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ role, content }),
    });
    if (!res.ok) return null;
    const conv = (await res.json()) as Conversation;
    return conv.messages;
  } catch {
    return null;
  }
}

export async function listConversations(): Promise<ConversationSummary[] | null> {
  try {
    const res = await fetch("/api/conversations");
    if (!res.ok) return null;
    return (await res.json()) as ConversationSummary[];
  } catch {
    return null;
  }
}

export async function runAgent(task: string): Promise<AgentRunResponse> {
  let res: Response;
  try {
    res = await fetch("/api/agent/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ task }),
    });
  } catch (err) {
    return { ok: false, error: `network error: ${err}`, steps: [] };
  }
  if (!res.ok) {
    return { ok: false, error: `server error ${res.status}: ${await res.text()}`, steps: [] };
  }
  return (await res.json()) as AgentRunResponse;
}

export async function streamAgent(
  task: string,
  onStep: (step: ToolStep) => void,
  history?: { role: "user" | "assistant"; content: string }[],
  onAnswerToken?: (delta: string) => void,
  conversationId?: string,
): Promise<AgentRunResponse> {
  let res: Response;
  try {
    res = await fetch("/api/agent/run/stream", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        task,
        history: history ?? [],
        conversation_id: conversationId ?? null,
      }),
    });
  } catch (err) {
    return { ok: false, error: `network error: ${err}`, steps: [] };
  }
  if (!res.ok || !res.body) {
    return { ok: false, error: `server error ${res.status}: ${await res.text()}`, steps: [] };
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const steps: ToolStep[] = [];
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "step") {
        steps.push(payload as ToolStep);
        onStep(payload as ToolStep);
      } else if (event === "answer_token") {
        onAnswerToken?.((payload as { delta: string }).delta);
      } else if (event === "result") {
        return payload as AgentRunResponse;
      } else if (event === "error") {
        return { ok: false, error: payload.error as string, steps };
      }
    }
  }
  return { ok: false, error: "stream ended without a result", steps };
}
