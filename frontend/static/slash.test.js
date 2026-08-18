/* Unit tests for the slash-command parser. Run: node --test frontend/static/slash.test.js */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { tokenize, parseSlashCommand } = require("./slash.js");

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
