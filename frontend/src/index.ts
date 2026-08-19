import { serve } from "bun";
import index from "./index.html";

const ORCHESTRATOR_URL = process.env.BUN_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";
const GATEWAY_URL = process.env.BUN_GATEWAY_URL ?? "http://127.0.0.1:8080";

async function forwardJson(
  url: string,
  method: string,
  body?: string,
): Promise<Response> {
  try {
    const res = await fetch(url, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body,
    });
    return new Response(res.body, {
      status: res.status,
      headers: { "content-type": "application/json" },
    });
  } catch (err) {
    return Response.json({ error: `orchestrator unreachable: ${err}` }, { status: 502 });
  }
}

const server = serve({
  routes: {
    // Serve index.html for all unmatched routes.
    "/*": index,
    "/api/health": async () => {
      try {
        const res = await fetch(`${ORCHESTRATOR_URL}/health`);
        return new Response(res.body, { status: res.status });
      } catch (err) {
        return Response.json({ status: "down" }, { status: 502 });
      }
    },

    "/api/agent/run": async req => {
      try {
        const res = await fetch(`${ORCHESTRATOR_URL}/agent/run`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: await req.text(),
        });
        return new Response(res.body, {
          status: res.status,
          headers: { "content-type": "application/json" },
        });
      } catch (err) {
        return Response.json(
          { ok: false, error: `orchestrator unreachable: ${err}`, steps: [] },
          { status: 502 },
        );
      }
    },

    "/api/agent/run/stream": async req => {
      try {
        const res = await fetch(`${ORCHESTRATOR_URL}/agent/run/stream`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: await req.text(),
        });
        return new Response(res.body, {
          status: res.status,
          headers: {
            "content-type": "text/event-stream",
            "cache-control": "no-cache",
            connection: "keep-alive",
          },
        });
      } catch (err) {
        return Response.json(
          { ok: false, error: `orchestrator unreachable: ${err}`, steps: [] },
          { status: 502 },
        );
      }
    },

    "/api/sessions/stats": async () => {
      try {
        const res = await fetch(`${GATEWAY_URL}/sessions/stats`);
        return new Response(res.body, {
          status: res.status,
          headers: { "content-type": "application/json" },
        });
      } catch (err) {
        return Response.json(
          {
            live_sessions: null,
            max_sessions: null,
            live_containers: null,
            stale_containers: null,
          },
          { status: 502 },
        );
      }
    },

    "/api/conversations": {
      async POST() {
        return forwardJson(`${ORCHESTRATOR_URL}/conversations`, "POST");
      },
      async GET() {
        return forwardJson(`${ORCHESTRATOR_URL}/conversations`, "GET");
      },
    },

    "/api/conversations/:id": async req => {
      return forwardJson(`${ORCHESTRATOR_URL}/conversations/${req.params.id}`, "GET");
    },

    "/api/conversations/:id/messages": async req => {
      return forwardJson(
        `${ORCHESTRATOR_URL}/conversations/${req.params.id}/messages`,
        "POST",
        await req.text(),
      );
    },

    "/api/hello": {
      async GET(req) {
        return Response.json({
          message: "Hello, world!",
          method: "GET",
        });
      },
      async PUT(req) {
        return Response.json({
          message: "Hello, world!",
          method: "PUT",
        });
      },
    },

    "/api/hello/:name": async req => {
      const name = req.params.name;
      return Response.json({
        message: `Hello, ${name}!`,
      });
    },
  },

  development: process.env.NODE_ENV !== "production" && {
    // Enable browser hot reloading in development
    hmr: true,

    // Echo console logs from the browser to the server
    console: true,
  },

  // Long-running agent streams can sit idle between tool steps (Docker
  // cold starts, slow models); the 10s default killed mid-run SSE.
  idleTimeout: 180,
});

console.log(`🚀 Server running at ${server.url}`);
