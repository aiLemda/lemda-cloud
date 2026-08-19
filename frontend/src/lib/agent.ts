export type ToolResult = {
  exit_code: number | null;
  stdout: string;
  stderr: string;
  timed_out: boolean;
  duration_ms: number;
};

export type ToolStep = {
  type: "tool";
  cmd: string;
  result: ToolResult;
};

export type AgentRunResponse = {
  ok: boolean;
  answer?: string;
  error?: string;
  steps: ToolStep[];
};

export type HealthResponse = {
  status: string;
  service?: string;
};

export type SessionStats = {
  live_sessions: number | null;
  max_sessions: number | null;
  live_containers: number | null;
  stale_containers: number | null;
};

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
};

export type Conversation = {
  id: string;
  messages: ChatTurn[];
};

export type ConversationSummary = {
  id: string;
  message_count: number;
  updated_at: number;
  preview: string;
};
