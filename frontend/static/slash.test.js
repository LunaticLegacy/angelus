/* Unit tests for the slash-command parser. Run: node --test frontend/static/slash.test.js */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  tokenize,
  parseSlashCommand,
  SLASH_COMMANDS,
  slashAvailability,
  slashPaletteState,
  applySlashSuggestion,
} = require("./slash.js");

test("tokenize splits on whitespace", () => {
  assert.deepEqual(tokenize("new 资料检索"), ["new", "资料检索"]);
  assert.deepEqual(tokenize("  a   b\tc\n"), ["a", "b", "c"]);
});

test("tokenize groups double-quoted tokens and honors escapes", () => {
  assert.deepEqual(tokenize('switch "我的 会话"'), ["switch", "我的 会话"]);
  assert.deepEqual(tokenize('new "a \\"quoted\\" name"'), ["new", 'a "quoted" name']);
  assert.deepEqual(tokenize('x "a\\\\b"'), ["x", "a\\b"]);
});

test("tokenize treats single quotes as literal groups", () => {
  assert.deepEqual(tokenize("switch 'my session'"), ["switch", "my session"]);
  assert.deepEqual(tokenize("x 'a\\b'"), ["x", "a\\b"]);
});

test("tokenize supports backslash escapes outside quotes", () => {
  assert.deepEqual(tokenize("new 我的\\ 会话"), ["new", "我的 会话"]);
  assert.deepEqual(tokenize("x\\ y"), ["x y"]);
});

test("tokenize handles empty input", () => {
  assert.deepEqual(tokenize(""), []);
  assert.deepEqual(tokenize("   "), []);
});

test("parse returns null for non-commands and literal //", () => {
  assert.equal(parseSlashCommand("你好"), null);
  assert.equal(parseSlashCommand("//not a command"), null);
  assert.equal(parseSlashCommand(""), null);
  assert.equal(parseSlashCommand("/"), null);
  assert.equal(parseSlashCommand(null), null);
});

test("parse splits command, args, and flags", () => {
  assert.deepEqual(parseSlashCommand("/compact --agent=coordinator"), {
    command: "compact",
    args: [],
    flags: { agent: "coordinator" },
  });
  assert.deepEqual(parseSlashCommand("/switch \"我的 会话\" --fresh"), {
    command: "switch",
    args: ["我的 会话"],
    flags: { fresh: true },
  });
});

test("parse lowercases the command but not args", () => {
  const parsed = parseSlashCommand("/NEW 资料检索");
  assert.equal(parsed.command, "new");
  assert.deepEqual(parsed.args, ["资料检索"]);
});

test("parse supports Unicode args and quoted names", () => {
  const parsed = parseSlashCommand('/new "项目 计划书"');
  assert.deepEqual(parsed.args, ["项目 计划书"]);
});

const byName = (name) => SLASH_COMMANDS.find((entry) => entry.command === name);

test("the catalog describes every command exactly once", () => {
  const names = SLASH_COMMANDS.map((entry) => entry.command);
  assert.equal(new Set(names).size, names.length);
  for (const entry of SLASH_COMMANDS) {
    assert.ok(entry.command && entry.group && entry.description, `incomplete entry ${entry.command}`);
  }
  // `/help` and the palette both render this list, so it must stay flat enough
  // to render: one command per row, no combined rows.
  assert.equal(names.includes("plan agents usage trace"), false);
});

test("palette opens on a bare slash and lists the whole catalog", () => {
  const state = slashPaletteState("/");
  assert.equal(state.open, true);
  assert.equal(state.mode, "commands");
  assert.deepEqual(state.matches.map((entry) => entry.command), SLASH_COMMANDS.map((entry) => entry.command));
});

test("palette filters the command word by prefix, case-insensitively", () => {
  assert.deepEqual(slashPaletteState("/co").matches.map((entry) => entry.command), ["compact", "connectors"]);
  assert.deepEqual(slashPaletteState("/CO").matches.map((entry) => entry.command), ["compact", "connectors"]);
  assert.equal(slashPaletteState("/zz").open, false);
});

test("palette stays closed for chat, escaped slashes and finished commands", () => {
  assert.equal(slashPaletteState("你好").open, false);
  assert.equal(slashPaletteState("//literal").open, false);
  assert.equal(slashPaletteState("/new 会话名").open, false);
  assert.equal(slashPaletteState("").open, false);
  assert.equal(slashPaletteState(undefined).open, false);
});

test("palette offers a command's named parameters after it", () => {
  const flags = slashPaletteState("/compact --");
  assert.equal(flags.mode, "flags");
  assert.deepEqual(flags.matches.map((flag) => flag.name), ["agent"]);
  assert.equal(flags.replaceFrom, "/compact ".length);
  assert.deepEqual(slashPaletteState("/settings --p").matches.map((flag) => flag.name), ["panel"]);
  assert.deepEqual(slashPaletteState("/compact -a").matches.map((flag) => flag.name), ["agent"]);
});

test("palette steps aside once a flag value is being typed", () => {
  assert.equal(slashPaletteState("/compact --agent=").open, false);
  assert.equal(slashPaletteState("/compact --agent=coordinator").open, false);
});

test("palette only offers parameters for commands that declare them", () => {
  assert.equal(slashPaletteState("/new --").open, false);
  assert.equal(slashPaletteState("/help --").open, false);
});

test("palette keeps offering parameters across a shifted-Enter line, as the parser does", () => {
  const state = slashPaletteState("/compact\n--a");
  assert.equal(state.mode, "flags");
  assert.deepEqual(state.matches.map((flag) => flag.name), ["agent"]);
  assert.equal(parseSlashCommand("/compact\n--a").flags.a, true);
});

test("accepting replaces the whole word under the caret", () => {
  // The caret sits inside the word, so the tail after it must go too.
  const midwayCommand = slashPaletteState("/compact", 4);
  assert.equal(midwayCommand.replaceTo, "/compact".length);
  assert.deepEqual(applySlashSuggestion("/compact", midwayCommand, { command: "compact" }), { value: "/compact ", caret: 9 });

  const midwayFlag = slashPaletteState("/compact --agent", 12);
  assert.equal(midwayFlag.replaceTo, "/compact --agent".length);
  assert.deepEqual(applySlashSuggestion("/compact --agent", midwayFlag, { name: "agent" }), { value: "/compact --agent=", caret: 17 });
});

test("nothing is applied without an open palette or a chosen match", () => {
  assert.equal(applySlashSuggestion("/co", slashPaletteState("你好"), { command: "compact" }), null);
  assert.equal(applySlashSuggestion("你好", slashPaletteState("你好"), null), null);
});

test("availability badges name the state each command needs", () => {
  assert.equal(slashAvailability(byName("stop"), { running: false }), "需运行中");
  assert.equal(slashAvailability(byName("stop"), { running: true }), "");
  assert.equal(slashAvailability(byName("compact"), { running: true }), "运行中不可用");
  assert.equal(slashAvailability(byName("compact"), { running: false }), "");
  assert.equal(slashAvailability(byName("switch"), { hasSession: false }), "需会话");
  assert.equal(slashAvailability(byName("help"), {}), "");
  assert.equal(slashAvailability(null, {}), "");
});
