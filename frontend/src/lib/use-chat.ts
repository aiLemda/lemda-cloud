import { useCallback, useEffect, useState } from "react";

import type { ToolStep } from "./agent";
import { appendConversationMessage, createConversation, getConversation, streamAgent } from "./client";

export type ChatMessage = {
  role: "user" | "agent";
  content: string;
};

export type ChatState = "idle" | "running" | "done" | "error";

const CONVERSATION_KEY = "devin_clone_conversation_id";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [state, setState] = useState<ChatState>("idle");
  const [answer, setAnswer] = useState("");
  const [steps, setSteps] = useState<ToolStep[]>([]);
  const [error, setError] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);

  useEffect(() => {
    const savedId = localStorage.getItem(CONVERSATION_KEY);
    if (!savedId) return;
    getConversation(savedId).then(conv => {
      if (conv) {
        setConversationId(conv.id);
        setMessages(
          conv.messages.map(m => ({
            role: m.role === "user" ? "user" : "agent",
            content: m.content,
          })),
        );
      } else {
        localStorage.removeItem(CONVERSATION_KEY);
      }
    });
  }, []);

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

      let convId = conversationId;
      if (!convId) {
        const conv = await createConversation();
        if (conv) {
          convId = conv.id;
          setConversationId(conv.id);
          localStorage.setItem(CONVERSATION_KEY, conv.id);
        }
      }
      if (convId) {
        await appendConversationMessage(convId, "user", trimmed);
      }

      const res = await streamAgent(
        trimmed,
        step => setSteps(prev => [...prev, step]),
        history,
        delta => setAnswer(prev => prev + delta),
      );
      const answerText = res.answer ?? res.error ?? "";
      setMessages(prev => [...prev, { role: "agent", content: answerText }]);
      if (convId) {
        await appendConversationMessage(convId, "assistant", answerText);
      }
      if (res.ok) {
        setAnswer(res.answer ?? "");
        setSteps(res.steps);
        setState("done");
      } else {
        setError(res.error ?? "unknown error");
        setState("error");
      }
    },
    [state, messages, conversationId],
  );

  const reset = useCallback(() => {
    setMessages([]);
    setState("idle");
    setAnswer("");
    setSteps([]);
    setError("");
    setConversationId(null);
    localStorage.removeItem(CONVERSATION_KEY);
  }, []);

  return { messages, state, answer, steps, error, conversationId, submit, reset };
}
