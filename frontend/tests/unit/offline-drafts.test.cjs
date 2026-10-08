const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

function loadModule(file) {
  const code = ts.transpileModule(fs.readFileSync(path.resolve(__dirname, "../../src/offline", file), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const exports = {};
  new Function("exports", code)(exports);
  return exports;
}
const { DraftSession } = loadModule("draftSession.ts");
function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}
function store(initial = null) {
  const values = new Map(initial === null ? [] : [["draft", initial]]);
  return { values, load: async (key) => values.get(key) ?? null,
    save: async (key, value) => { values.set(key, value); }, remove: async (key) => { values.delete(key); } };
}

test("slow restoration cannot overwrite freshly entered text", async () => {
  const pending = deferred();
  const session = new DraftSession("draft", "", { ...store(), load: () => pending.promise });
  const restore = session.restore();
  session.update("Новый текст");
  pending.resolve("Старый черновик");
  await restore;
  assert.equal(session.getSnapshot().value, "Новый текст");
  assert.equal(session.getSnapshot().restored, false);
});
test("restored empty and nonempty drafts are distinct from a missing draft", async () => {
  for (const saved of ["", "Сохранено"]) {
    const session = new DraftSession("draft", "Начальное", store(saved));
    await session.restore();
    assert.equal(session.getSnapshot().value, saved);
    assert.equal(session.getSnapshot().restored, true);
  }
});
test("editing and then erasing a draft replaces the previous saved text", async () => {
  const storage = store("Старый текст");
  const session = new DraftSession("draft", "", storage);
  await session.restore(); session.update(""); await session.flush();
  assert.equal(storage.values.get("draft"), "");
});
test("late restoration of a closed chat does not publish another chat's text", async () => {
  const pending = deferred();
  const session = new DraftSession("chat:1", "", { ...store(), load: () => pending.promise });
  let emissions = 0;
  session.subscribe(() => { emissions += 1; });
  const restore = session.restore(); session.close(); pending.resolve("Чужой текст"); await restore;
  assert.equal(emissions, 0);
});
test("leaving the page flushes dirty data", async () => {
  const storage = store();
  const session = new DraftSession("draft", "", storage);
  await session.restore(); session.update("Сохранить при выходе"); session.close(); await session.flush();
  assert.equal(storage.values.get("draft"), "Сохранить при выходе");
});
test("concurrent flushes of the same revision make one write", async () => {
  const pending = deferred(); let writes = 0;
  const session = new DraftSession("draft", "", { ...store(), save: async () => { writes += 1; await pending.promise; } });
  await session.restore(); session.update("Текст");
  const first = session.flush(); const second = session.flush();
  assert.equal(first, second); assert.equal(writes, 1);
  pending.resolve(); await first;
});
test("an older in-flight write does not mark newer text as saved", async () => {
  const pending = deferred();
  const session = new DraftSession("draft", "", { ...store(), save: () => pending.promise });
  await session.restore(); session.update("Первая версия"); const flush = session.flush();
  session.update("Вторая версия"); pending.resolve(); await flush;
  assert.equal(session.getSnapshot().dirty, true);
  assert.equal(session.getSnapshot().value, "Вторая версия");
});
test("clearing a sent draft resets the form and removes persisted data", async () => {
  const storage = store("Текст"); const session = new DraftSession("draft", "", storage);
  await session.restore(); await session.clear();
  assert.equal(session.getSnapshot().value, ""); assert.equal(session.getSnapshot().dirty, false);
  assert.equal(storage.values.has("draft"), false);
});
test("clearing an old conversation leaves the new conversation's draft intact", async () => {
  const storage = store();
  const first = new DraftSession("chat:1", "", storage); const second = new DraftSession("chat:2", "", storage);
  await first.restore(); await second.restore();
  first.update("Первый"); second.update("Второй"); await first.flush(); await second.flush();
  await first.clear(); assert.equal(second.getSnapshot().value, "Второй"); assert.equal(storage.values.get("chat:2"), "Второй");
});
test("unavailable IndexedDB preserves data in memory and signals its limitation", async () => {
  const storage = loadModule("storage.ts"); let changed = 0;
  const unsubscribe = storage.subscribeOfflineStorage(() => { changed += 1; });
  const form = { subject: "Тема" }; await storage.saveOfflineValue("draft", form); form.subject = "Изменено";
  assert.equal(storage.getOfflineStorageMode(), "memory"); assert.equal(changed, 1);
  assert.deepEqual(await storage.loadOfflineValue("draft"), { subject: "Тема" });
  await storage.deleteOfflineValue("draft"); assert.equal(await storage.loadOfflineValue("draft"), null);
  unsubscribe();
});
test("save/delete/read ordering prevents a sent draft from reappearing", async () => {
  const storage = loadModule("storage.ts");
  const write = storage.saveOfflineValue("draft", "Отправлено");
  const remove = storage.deleteOfflineValue("draft");
  const read = storage.loadOfflineValue("draft");
  await Promise.all([write, remove]); assert.equal(await read, null);
});
test("offline cache cannot conceal access revocation or cancelled requests", () => {
  const { canUseOfflineCache } = loadModule("cachePolicy.ts");
  for (const status of [400, 401, 403, 404, 422, 429]) assert.equal(canUseOfflineCache({ response: { status } }), false);
  for (const error of [{ code: "ERR_CANCELED" }, { name: "AbortError" }, { name: "CanceledError" }]) assert.equal(canUseOfflineCache(error), false);
});
test("offline cache is available during network or server failures", () => {
  const { canUseOfflineCache } = loadModule("cachePolicy.ts");
  assert.equal(canUseOfflineCache({ code: "ERR_NETWORK" }), true);
  assert.equal(canUseOfflineCache({ response: { status: 503 } }), true);
});

test("leaving during slow restore still saves newly entered data", async () => {
  const pending = deferred(); const storage = store();
  const session = new DraftSession("draft", "", { ...storage, load: () => pending.promise });
  const restore = session.restore(); session.update("Новые данные"); session.close();
  pending.resolve("Старые данные"); await restore;
  assert.equal(storage.values.get("draft"), "Новые данные");
});
test("clear during restore cannot resurrect an old draft", async () => {
  const pending = deferred(); const storage = store("Old");
  const session = new DraftSession("draft", "", { ...storage, load: () => pending.promise });
  const restore = session.restore(); await session.clear(); pending.resolve("Old"); await restore;
  assert.equal(session.getSnapshot().value, ""); assert.equal(storage.values.has("draft"), false);
});
test("completion of a cleared write cannot report the form as saved", async () => {
  const pending = deferred();
  const session = new DraftSession("draft", "", { ...store(), save: () => pending.promise });
  await session.restore(); session.update("Text"); const save = session.flush(); await session.clear();
  pending.resolve(); await save;
  assert.equal(session.getSnapshot().savedAt, null); assert.equal(session.getSnapshot().dirty, false);
});
