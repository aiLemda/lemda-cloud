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
