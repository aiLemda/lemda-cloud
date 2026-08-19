import { useCallback, useEffect, useState } from "react";

import type { ConversationSummary, ToolStep } from "./agent";
import {
  appendConversationMessage,
  createConversation,
  getConversation,
  listConversations,
  streamAgent,
} from "./client";

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
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);

  const refreshConversations = useCallback(() => {
    listConversations().then(list => {
      if (list) setConversations(list);
    });
  }, []);

  useEffect(() => {
    refreshConversations();
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
  }, [refreshConversations]);

  const selectConversation = useCallback(
    async (id: string) => {
      if (state === "running") return;
      const conv = await getConversation(id);
      if (!conv) return;
      setConversationId(id);
      localStorage.setItem(CONVERSATION_KEY, id);
      setMessages(
        conv.messages.map(m => ({
          role: m.role === "user" ? "user" : "agent",
          content: m.content,
        })),
      );
      setState("done");
      setAnswer("");
      setSteps([]);
      setError("");
      refreshConversations();
    },
    [state, refreshConversations],
  );

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
          refreshConversations();
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
        convId ?? undefined,
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
    refreshConversations();
  }, [refreshConversations]);

  return {
    messages,
    state,
    answer,
    steps,
    error,
    conversationId,
    conversations,
    submit,
    reset,
    selectConversation,
  };
}
