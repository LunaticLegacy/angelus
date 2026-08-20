/** Cross-platform launcher for the Python desktop-sidecar builder.
 *
 * npm already guarantees Node is available.  Resolve Python without a shell
 * so Windows, macOS, and Linux do not depend on Bash, WSL, or Git Bash.
 */
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(scriptsDir, "..");
const builder = join(scriptsDir, "build_backend.py");
const windows = process.platform === "win32";
const candidates = [];

if (process.env.ANGELUS_PYTHON) candidates.push({ command: process.env.ANGELUS_PYTHON, prefix: [] });
const venvPython = windows
  ? join(rootDir, ".venv", "Scripts", "python.exe")
  : join(rootDir, ".venv", "bin", "python");
if (existsSync(venvPython)) candidates.push({ command: venvPython, prefix: [] });
if (windows) candidates.push({ command: "python", prefix: [] }, { command: "py", prefix: ["-3"] });
else candidates.push({ command: "python3", prefix: [] }, { command: "python", prefix: [] });

const python = candidates.find(({ command, prefix }) =>
  spawnSync(command, [...prefix, "--version"], { stdio: "ignore" }).status === 0,
);
if (!python) {
  console.error("Python 3 was not found. Set ANGELUS_PYTHON to its executable path.");
  process.exit(1);
}

const result = spawnSync(python.command, [...python.prefix, builder], {
  cwd: rootDir,
  env: process.env,
  stdio: "inherit",
});
if (result.error) {
  console.error(`Unable to start Python: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
