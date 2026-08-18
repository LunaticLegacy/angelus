/* Slash-command parsing for the Angelus chat composer.
 *
 * Pure, DOM-free module so the parser can be unit-tested with `node --test`
 * while also loading as a plain browser script (no bundler).  The grammar is
 * a small shell-style subset:
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

if (typeof module !== "undefined" && module.exports) {
  module.exports = { tokenize, parseSlashCommand };
}
