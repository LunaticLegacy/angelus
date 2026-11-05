import { readFile } from "node:fs/promises";

const root = new URL("../frontend/", import.meta.url);
const staticRoot = new URL("../frontend/static/", import.meta.url);
const template = await readFile(new URL("../frontend/templates/index.html", import.meta.url), "utf8");

const errors = [];
const legacy = ["main.js", "chat.js", "sessions.js", "settings.js", "connectors.js", "events.js", "state.js", "utils.js"];
const active = [
  "app.js",
  "app-loader.js",
  "plugins.js",
  "external-agents.js",
  "i18n.js",
  "runtime/backend-bridge.js",
  "runtime/session-api.js",
  "runtime/connector-api.js",
  "runtime/settings-api.js",
  "runtime/plugin-api.js",
  "runtime/mcp-api.js",
  "runtime/inspector-api.js",
  "runtime/run-api.js",
  "ui/shell.js",
  "ui/icons.js",
  "components/external-agent-hub-view.js",
  "components/session-list.js",
  "components/composer-scope.js",
  "components/connector-select.js",
  "components/notes-view.js",
  "controllers/session-controller.js",
  "controllers/connector-controller.js",
  "controllers/stream-controller.js",
  "controllers/run-stream-controller.js",
  "controllers/plugin-controller.js",
  "controllers/mcp-controller.js",
  "controllers/settings-controller.js",
  "controllers/run-controller.js",
  "controllers/inspector-controller.js",
  "controllers/agent-state-controller.js",
];

if ((template.match(/<script[^>]+src="\/static\/[^" ]+\.js/g) || []).length !== 2) {
  errors.push("index.html must keep exactly two browser script entries: slash.js and app-loader.js");
}
if (!template.includes('src="/static/app-loader.js')) errors.push("index.html must load app-loader.js");
if (!await readFile(new URL("app-loader.js", staticRoot), "utf8").then((source) => source.includes("/static/app.js"))) {
  errors.push("app-loader.js must import app.js");
}

for (const file of active) {
  const source = await readFile(new URL(file, staticRoot), "utf8");
  const isRuntime = file.startsWith("runtime/");
  if (!isRuntime && /\bfetch\s*\(|\bnew\s+EventSource\s*\(/.test(source)) {
    errors.push(`${file} contains direct transport construction outside runtime/`);
  }
}

for (const file of legacy) {
  if (template.includes(`/static/${file}`)) errors.push(`template still mounts legacy module ${file}`);
}

if (errors.length) {
  console.error(errors.map((error) => `- ${error}`).join("\n"));
  process.exitCode = 1;
} else {
  console.log("frontend architecture check passed");
}
