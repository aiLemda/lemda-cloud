import type { ToolStep } from "@/lib/agent";
import { cn } from "@/lib/utils";

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function StepCard({ step }: { step: ToolStep }) {
  const r = step.result;
  const ok = r.exit_code === 0;
  const hasOutput = Boolean(r.stdout) || Boolean(r.stderr);
  return (
    <div className="rounded-lg border bg-muted/40 p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          🧠 think
        </span>
        <code className="rounded bg-background px-2 py-0.5 font-mono text-xs">
          run_bash({JSON.stringify(step.cmd)})
        </code>
        <span
          className={cn(
            "ml-auto rounded px-1.5 py-0.5 font-mono text-xs",
            ok ? "bg-emerald-500/15 text-emerald-600" : "bg-red-500/15 text-red-600",
          )}
        >
          exit {r.exit_code ?? "—"}
        </span>
        <span className="font-mono text-xs text-muted-foreground">{formatMs(r.duration_ms)}</span>
      </div>
      {r.timed_out && (
        <p className="mt-2 text-xs font-semibold text-amber-600">⏰ timed out — container killed</p>
      )}
      <div className="mt-2 flex items-center gap-2 text-sm">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          👀 look
        </span>
        {hasOutput ? (
          <details className="min-w-0 flex-1">
            <summary className="cursor-pointer font-mono text-xs text-muted-foreground hover:text-foreground">
              see output
            </summary>
            <pre className="mt-2 max-h-56 overflow-auto rounded bg-background p-2 font-mono text-xs whitespace-pre-wrap">
              {r.stderr && (
                <>
                  <span className="text-red-600">{r.stderr}</span>
                  {r.stdout && "\n"}
                </>
              )}
              {r.stdout}
            </pre>
          </details>
        ) : (
          <span className="font-mono text-xs text-muted-foreground">no output</span>
        )}
      </div>
    </div>
  );
}

export function TraceViewer({ steps }: { steps: ToolStep[] }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        🤖 robot diary — {steps.length} step{steps.length === 1 ? "" : "s"}
      </p>
      {steps.map((step, i) => (
        <StepCard key={i} step={step} />
      ))}
    </div>
  );
}
