import { useCallback, useState } from "react";

import type { ToolStep } from "./agent";
import { streamAgent } from "./client";

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
      const history: { role: "user" | "assistant"; content: string }[] = messages
        .slice(-10)
        .map(m => ({ role: m.role === "user" ? "user" : "assistant", content: m.content }));
      setMessages(prev => [...prev, { role: "user", content: trimmed }]);
      setState("running");
      setAnswer("");
      setSteps([]);
      setError("");
      const res = await streamAgent(
        trimmed,
        step => setSteps(prev => [...prev, step]),
        history,
        delta => setAnswer(prev => prev + delta),
      );
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
    [state, messages],
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
