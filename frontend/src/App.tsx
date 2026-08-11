import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { checkHealth } from "@/lib/client";
import { useChat } from "@/lib/use-chat";
import { cn } from "@/lib/utils";
import { TraceViewer } from "@/components/trace-viewer";
import { APITester } from "./APITester";

export function App() {
  const { messages, state, answer, steps, error, submit } = useChat();
  const [task, setTask] = useState("");
  const [online, setOnline] = useState<boolean | null>(null);
  const [view, setView] = useState<"chat" | "debug">("chat");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    checkHealth().then(h => setOnline(h.status === "ok"));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, state]);

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!task.trim() || state === "running") return;
    void submit(task);
    setTask("");
  };

  return (
    <div className="flex h-screen w-full max-w-3xl flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold">🤖 the robot</h1>
        <div className="flex items-center gap-3">
          <div className="flex rounded-md border p-0.5 text-xs">
            <button
              onClick={() => setView("chat")}
              className={cn(
                "rounded px-2 py-1 font-medium",
                view === "chat" ? "bg-primary text-primary-foreground" : "text-muted-foreground",
              )}
            >
              chat
            </button>
            <button
              onClick={() => setView("debug")}
              className={cn(
                "rounded px-2 py-1 font-medium",
                view === "debug" ? "bg-primary text-primary-foreground" : "text-muted-foreground",
              )}
            >
              debug
            </button>
          </div>
          <span
            className={cn(
              "flex items-center gap-1.5 text-xs font-medium",
              online === null ? "text-muted-foreground" : online ? "text-emerald-600" : "text-red-600",
            )}
          >
            <span
              className={cn(
                "size-2 rounded-full",
                online === null ? "bg-muted-foreground" : online ? "bg-emerald-500" : "bg-red-500",
              )}
            />
            {online === null ? "checking…" : online ? "robot online" : "robot offline"}
          </span>
        </div>
      </header>

      {view === "debug" && (
        <Card>
          <CardContent className="p-4">
            <APITester />
          </CardContent>
        </Card>
      )}

      <Card className="flex min-h-0 flex-1 flex-col">
        <CardContent className="flex min-h-0 flex-1 flex-col gap-4 p-4">
          <div ref={scrollRef} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
            {messages.length === 0 && state === "idle" && (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
                <p className="text-4xl">🤖</p>
                <p className="text-sm font-medium">What should the robot do?</p>
                <p className="text-xs">Try: “list the files in the sandbox root and tell me the Python version”</p>
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div
                  className={cn(
                    "max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap",
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-foreground",
                  )}
                >
                  {m.content}
                </div>
              </div>
            ))}

            {state === "running" && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-2xl bg-muted px-4 py-2 text-sm text-muted-foreground">
                  <span className="animate-pulse">🧠 thinking…</span>
                </div>
              </div>
            )}

            {state === "done" && answer && (
              <div className="flex flex-col gap-3">
                <div className="flex justify-start">
                  <div className="rounded-2xl bg-muted px-4 py-2 text-sm whitespace-pre-wrap">
                    {answer}
                  </div>
                </div>
                {steps.length > 0 && <TraceViewer steps={steps} />}
              </div>
            )}

            {state === "error" && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-2xl border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-700">
                  <p className="font-semibold">the robot tripped</p>
                  <p className="mt-1 font-mono text-xs whitespace-pre-wrap">{error}</p>
                </div>
              </div>
            )}
          </div>

          <form onSubmit={onSubmit} className="flex shrink-0 gap-2">
            <Input
              value={task}
              onChange={e => setTask(e.target.value)}
              placeholder="tell the robot what to do…"
              disabled={state === "running"}
              className="flex-1"
            />
            <Button type="submit" disabled={state === "running" || !task.trim()}>
              Send
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export default App;
