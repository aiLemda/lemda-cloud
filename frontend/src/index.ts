import { serve } from "bun";
import index from "./index.html";

const ORCHESTRATOR_URL = process.env.BUN_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";
const GATEWAY_URL = process.env.BUN_GATEWAY_URL ?? "http://127.0.0.1:8080";

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
});

console.log(`🚀 Server running at ${server.url}`);
