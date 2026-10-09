/* Slash-command parsing for the Angelus chat composer.
 *
 * Pure, DOM-free module so the parser and the palette's matching logic can be
 * unit-tested with `node --test` while also loading as a plain browser script
 * (no bundler).  The grammar is a small shell-style subset:
 *
 *   /command arg1 "arg with spaces" 'literal' --flag --key=value
 *
 * - whitespace separates tokens; quotes group tokens
 * - `"` supports `\"` and `\\` escapes; `'` is a literal group (no escapes)
 * - outside quotes a backslash escapes the next character (`\ ` -> space)
 * - `--flag` sets a boolean flag; `--key=value` sets a string flag
 * - tokens that are not flags are positional args
 * - lines that do not start with a single `/` (including `//`) return null,
 *   so ordinary chat and literal slash text pass straight through
 *
 * The same file owns the command catalog: `SLASH_COMMANDS` is the single
 * source of truth for what the composer's palette and `/help` show, while
 * `app.js` keeps the handlers that actually run them.
 */
"use strict";

function isWhitespace(ch) {
  return ch === " " || ch === "\t" || ch === "\n" || ch === "\r";
}

/** Split a shell-style command string into tokens (quote/escape aware). */
function tokenize(input) {
  const tokens = [];
  let i = 0;
  const n = input.length;
  while (i < n) {
    while (i < n && isWhitespace(input[i])) i += 1;
    if (i >= n) break;
    let token = "";
    let quote = null; // null | '"' | "'"
    while (i < n) {
      const ch = input[i];
      if (quote === null && (ch === '"' || ch === "'")) {
        quote = ch;
        i += 1;
        continue;
      }
      if (quote !== null && ch === quote) {
        quote = null;
        i += 1;
        continue;
      }
      if (quote === null && isWhitespace(ch)) break;
      if (ch === "\\" && i + 1 < n && quote !== "'") {
        token += input[i + 1];
        i += 2;
        continue;
      }
      token += ch;
      i += 1;
    }
    tokens.push(token);
  }
  return tokens;
}

/**
 * Parse one composer line into a slash command descriptor.
 *
 * @param {string} line
 * @returns {{command: string, args: string[], flags: Record<string, string|boolean>} | null}
 *   null when the line is not a slash command (or is the literal `//` escape).
 */
function parseSlashCommand(line) {
  if (typeof line !== "string") return null;
  if (!line.startsWith("/") || line.startsWith("//")) return null;
  const rest = line.slice(1);
  if (!rest.trim()) return null;
  const tokens = tokenize(rest);
  if (!tokens.length) return null;
  const command = tokens[0].toLowerCase();
  const args = [];
  const flags = {};
  for (const token of tokens.slice(1)) {
    if (token.startsWith("--")) {
      const body = token.slice(2);
      const eq = body.indexOf("=");
      if (eq === -1) flags[body] = true;
      else flags[body.slice(0, eq)] = body.slice(eq + 1);
    } else {
      args.push(token);
    }
  }
  return { command, args, flags };
}

/**
 * Every command the composer accepts, in the order a palette should show it.
 *
 * `requires` names the session state the command needs in order to act, so a
 * palette can badge a row instead of letting the user pick one and read an
 * error: `"running"` needs a run in flight, `"idle"` needs none, `"session"`
 * needs a selected session, and `null` always works. `flags` describes the
 * named parameters the command accepts.
 */
const SLASH_COMMANDS = [
  { command: "help", args: "", description: "显示全部斜杠指令", group: "指令", requires: null },
  { command: "new", args: "<会话名>", description: "创建并切换到新会话", group: "会话", requires: null },
  { command: "switch", args: "<会话名>", description: "切换到已有会话", group: "会话", requires: "session" },
  { command: "delete", args: "<会话名>", description: "删除会话（需确认）", group: "会话", requires: "session" },
  { command: "clear", args: "", description: "清空聊天区视图（会话记录仍保留）", group: "会话", requires: null },
  { command: "plan", args: "", description: "查看任务计划面板", group: "视图", requires: null },
  { command: "agents", args: "", description: "查看 Agent 面板", group: "视图", requires: null },
  { command: "usage", args: "", description: "查看用量面板", group: "视图", requires: null },
  { command: "trace", args: "", description: "查看 Trace 面板", group: "视图", requires: null },
  { command: "agent", args: "<agentId>", description: "只显示指定 Agent 的消息", group: "视图", requires: "session" },
  { command: "stop", args: "", description: "在安全边界停止当前运行", group: "运行", requires: "running" },
  { command: "force-stop", args: "", description: "中断当前模型请求并终止 Shell 工具", group: "运行", requires: "running" },
  {
    command: "compact",
    args: "[--agent=<id>]",
    description: "手动压缩上下文为摘要",
    group: "上下文",
    requires: "idle",
    flags: [{ name: "agent", value: "<id>", description: "目标 Agent，默认 coordinator" }],
  },
  { command: "connectors", args: "", description: "打开连接器设置", group: "设置", requires: null },
  {
    command: "settings",
    args: "[--panel=<名称>]",
    description: "直接打开设置里的某个面板",
    group: "设置",
    requires: null,
    flags: [
      {
        name: "panel",
        value: "<名称>",
        description: "connection / agent / permissions / mcp / plugins / language",
      },
    ],
  },
];

/** The closed palette, shared so callers can compare fields cheaply. */
const SLASH_PALETTE_CLOSED = {
  open: false,
  mode: "commands",
  matches: [],
  replaceFrom: 0,
  replaceTo: 0,
  command: "",
  query: "",
};

/**
 * Explain why a command cannot act right now.
 *
 * @param {object} entry Catalog entry carrying `requires`.
 * @param {{running?: boolean, hasSession?: boolean}} state Live composer state.
 * @returns {string} Empty when the command is available, else a short badge.
 */
function slashAvailability(entry, state) {
  if (!entry) return "";
  const running = Boolean(state && state.running);
  const hasSession = Boolean(state && state.hasSession);
  if (entry.requires === "running" && !running) return "需运行中";
  if (entry.requires === "idle" && running) return "运行中不可用";
  if (entry.requires === "session" && !hasSession) return "需会话";
  return "";
}

/**
 * Describe what the composer palette should offer for the text before a caret.
 *
 * The newline handling mirrors `parseSlashCommand`, which treats every
 * whitespace character (newlines included) as a separator, so a shifted-Enter
 * continuation of a command still offers that command's parameters.
 *
 * @param {string} value Whole textarea value.
 * @param {number} [caret] Caret offset; defaults to the end of the value.
 * @returns {{open: boolean, mode: string, matches: object[], replaceFrom: number,
 *   replaceTo: number, command: string, query: string}} Palette state, with
 *   absolute offsets ready to slice `value`.
 */
function slashPaletteState(value, caret) {
  if (typeof value !== "string") return { ...SLASH_PALETTE_CLOSED };
  const at = typeof caret === "number" ? Math.max(0, Math.min(caret, value.length)) : value.length;
  const prefix = value.slice(0, at);
  if (!prefix.startsWith("/") || prefix.startsWith("//")) return { ...SLASH_PALETTE_CLOSED };

  // Accepting a match replaces the whole word under the caret, including the
  // part the caret sits inside, so midway completion never leaves a tail.
  const breakAt = value.slice(at).search(/\s/);
  const wordEnd = breakAt === -1 ? value.length : at + breakAt;

  const firstBreak = prefix.search(/\s/);
  if (firstBreak === -1) {
    // Still typing the command word itself.
    const query = prefix.slice(1).toLowerCase();
    const matches = SLASH_COMMANDS.filter((entry) => entry.command.startsWith(query));
    return { open: matches.length > 0, mode: "commands", matches, replaceFrom: 0, replaceTo: wordEnd, command: "", query };
  }

  const command = prefix.slice(1, firstBreak).toLowerCase();
  const entry = SLASH_COMMANDS.find((item) => item.command === command);
  if (!entry || !Array.isArray(entry.flags) || !entry.flags.length) return { ...SLASH_PALETTE_CLOSED };

  const tokenStart = prefix.search(/\S+\s*$/);
  const token = value.slice(tokenStart, wordEnd);
  // A parameter is only completed while its name is being typed: once `=` is
  // in, the value belongs to the user and the panel steps aside.
  if (!token.startsWith("-") || token.includes("=")) return { ...SLASH_PALETTE_CLOSED };
  const query = token.replace(/^--?/, "").toLowerCase();
  const matches = entry.flags.filter((flag) => flag.name.startsWith(query));
  return {
    open: matches.length > 0,
    mode: "flags",
    matches,
    replaceFrom: tokenStart,
    replaceTo: wordEnd,
    command,
    query,
  };
}

/**
 * Rewrite the composer text to accept one palette match.
 *
 * @param {string} value Whole textarea value.
 * @param {object} state Palette state the match came from.
 * @param {object} match Chosen command entry or flag descriptor.
 * @returns {{value: string, caret: number} | null} The rewritten text and the
 *   caret to restore, or null when there is nothing to apply.
 */
function applySlashSuggestion(value, state, match) {
  if (!state || !state.open || !match) return null;
  const text = state.mode === "flags" ? `--${match.name}=` : `/${match.command} `;
  return {
    value: value.slice(0, state.replaceFrom) + text + value.slice(state.replaceTo),
    caret: state.replaceFrom + text.length,
  };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    tokenize,
    parseSlashCommand,
    SLASH_COMMANDS,
    slashAvailability,
    slashPaletteState,
    applySlashSuggestion,
  };
}
