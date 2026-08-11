import type { AgentRunResponse, HealthResponse } from "./agent";

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

export async function checkHealth(): Promise<HealthResponse> {
  try {
    const res = await fetch("/api/health");
    return (await res.json()) as HealthResponse;
  } catch {
    return { status: "down" };
  }
}
