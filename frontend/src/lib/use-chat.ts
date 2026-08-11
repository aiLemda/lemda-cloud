import { useCallback, useState } from "react";

import type { ToolStep } from "./agent";
import { runAgent } from "./client";

export type ChatMessage = {
  role: "user" | "agent";
  content: string;
};

export type ChatState = "idle" | "running" | "done" | "error";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [state, setState] = useState<ChatState>("idle");
  const [answer, setAnswer] = useState("");
  const [steps, setSteps] = useState<ToolStep[]>([]);
  const [error, setError] = useState("");

  const submit = useCallback(
    async (task: string) => {
      const trimmed = task.trim();
      if (!trimmed || state === "running") return;
      setMessages(prev => [...prev, { role: "user", content: trimmed }]);
      setState("running");
      setAnswer("");
      setSteps([]);
      setError("");
      const res = await runAgent(trimmed);
      setMessages(prev => [...prev, { role: "agent", content: res.answer ?? res.error ?? "" }]);
      if (res.ok) {
        setAnswer(res.answer ?? "");
        setSteps(res.steps);
        setState("done");
      } else {
        setError(res.error ?? "unknown error");
        setState("error");
      }
    },
    [state],
  );

  const reset = useCallback(() => {
    setMessages([]);
    setState("idle");
    setAnswer("");
    setSteps([]);
    setError("");
  }, []);

  return { messages, state, answer, steps, error, submit, reset };
}
