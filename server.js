import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { analyzeConversation } from "./src/analyzer.js";
import { parseSharedNetHtml, validateSharedNetUrl } from "./src/providers/sharednet.js";

const port = Number(process.env.PORT || 3000);
const isProduction = process.env.NODE_ENV === "production";
const distDir = resolve(fileURLToPath(new URL("./dist/", import.meta.url)));
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml"
};
const vite = isProduction
  ? null
  : await import("vite").then(({ createServer: createViteServer }) =>
      createViteServer({ server: { middlewareMode: true }, appType: "spa" })
    );

function sendJson(response, status, body) {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store"
  });
  response.end(JSON.stringify(body));
}

async function readJson(request) {
  const chunks = [];
  let size = 0;

  for await (const chunk of request) {
    size += chunk.length;
    if (size > 32_768) {
      throw new Error("Request body is too large.");
    }
    chunks.push(chunk);
  }

  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new Error("Request body must be valid JSON.");
  }
}

async function fetchSharedNetPage(input, redirectsRemaining = 3) {
  const url = validateSharedNetUrl(input);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);

  try {
    const result = await fetch(url, {
      headers: {
        "accept": "text/html",
        "user-agent": "Multi-Agent-Trace-Analysis/0.1"
      },
      redirect: "manual",
      signal: controller.signal
    });

    if (result.status >= 300 && result.status < 400) {
      if (!redirectsRemaining) {
        throw new Error("Too many redirects while loading the conversation.");
      }
      const location = result.headers.get("location");
      if (!location) {
        throw new Error("The conversation returned an invalid redirect.");
      }
      return fetchSharedNetPage(new URL(location, url).href, redirectsRemaining - 1);
    }

    if (!result.ok) {
      throw new Error(`SharedNet returned HTTP ${result.status}.`);
    }

    const contentType = result.headers.get("content-type") || "";
    if (!contentType.includes("text/html")) {
      throw new Error("The supplied URL did not return an HTML conversation.");
    }

    const declaredSize = Number(result.headers.get("content-length") || 0);
    if (declaredSize > 5_000_000) {
      throw new Error("The conversation is too large to analyze.");
    }

    const html = await result.text();
    if (Buffer.byteLength(html) > 5_000_000) {
      throw new Error("The conversation is too large to analyze.");
    }
    return { html, finalUrl: url.href };
  } finally {
    clearTimeout(timeout);
  }
}

async function serveProductionAsset(url, response) {
  const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
  const filePath = resolve(distDir, `.${pathname}`);
  if (filePath !== distDir && !filePath.startsWith(`${distDir}${sep}`)) {
    sendJson(response, 404, { error: "Not found." });
    return;
  }

  try {
    const content = await readFile(filePath);
    response.writeHead(200, {
      "content-type": contentTypes[extname(filePath)] || "application/octet-stream",
      "cache-control": pathname === "/index.html" ? "no-cache" : "public, max-age=31536000, immutable"
    });
    response.end(content);
  } catch (error) {
    if (error.code === "ENOENT") {
      sendJson(response, 404, { error: "Not found." });
      return;
    }
    throw error;
  }
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, `http://${request.headers.host || "localhost"}`);

    if (request.method === "POST" && url.pathname === "/api/analyze") {
      const body = await readJson(request);
      const { html, finalUrl } = await fetchSharedNetPage(body.url);
      const conversation = parseSharedNetHtml(html, finalUrl);
      sendJson(response, 200, analyzeConversation(conversation));
      return;
    }

    if (request.method === "GET" && vite) {
      vite.middlewares(request, response, (error) => {
        if (error) sendJson(response, 500, { error: error.message });
      });
      return;
    }

    if (request.method === "GET") {
      await serveProductionAsset(url, response);
      return;
    }

    sendJson(response, 405, { error: "Method not allowed." });
  } catch (error) {
    const message = error.name === "AbortError"
      ? "SharedNet did not respond before the 15 second timeout."
      : error.message;
    sendJson(response, 400, { error: message });
  }
});

server.listen(port, () => {
  console.log(`TraceScope running at http://localhost:${port}`);
});
