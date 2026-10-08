const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

function loadStorage(indexedDB, navigator) {
  const code = ts.transpileModule(fs.readFileSync(path.resolve(__dirname, "../../src/offline/storage.ts"), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const exports = {};
  new Function("exports", "indexedDB", "navigator", code)(exports, indexedDB, navigator);
  return exports;
}
function fakeDatabase(values = new Map(), options = {}) {
  const state = { closed: 0, pending: [], lateOpen: null };
  function database() {
    return { objectStoreNames: { contains: () => true }, close: () => { state.closed += 1; },
      transaction(_name, mode) {
        const transaction = { error: new Error("Storage failure") };
        const commit = (operation) => {
          const finish = () => {
            if (options.abortWrites) transaction.onabort?.();
            else { operation(); transaction.oncomplete?.(); }
          };
          if (options.holdWrites && mode === "readwrite") state.pending.push(finish);
          else queueMicrotask(finish);
        };
        transaction.objectStore = () => ({
          put: (record) => commit(() => values.set(record.key, structuredClone(record))),
          delete: (key) => commit(() => values.delete(key)),
          get: (key) => {
            const request = { error: new Error("Read failed") };
            queueMicrotask(() => {
              if (options.abortReads) transaction.onabort?.();
              else { request.result = structuredClone(values.get(key)); request.onsuccess?.(); }
            });
            return request;
          },
        });
        return transaction;
      },
    };
  }
  return { values, state, open() {
    const request = { error: new Error("Open failed") };
    queueMicrotask(() => {
      if (options.blocked) { state.lateOpen = request; request.onblocked?.(); }
      else if (options.openError) request.onerror?.();
      else { request.result = database(); request.onsuccess?.(); }
    });
    state.finishLateOpen = () => { state.lateOpen.result = database(); state.lateOpen.onsuccess(); };
    return request;
  } };
}

test("persistent restore closes the database and returns a defensive copy", async () => {
  const database = fakeDatabase(new Map([["draft", { key: "draft", value: { text: "Saved" } }]]));
  const storage = loadStorage(database);
  const first = await storage.loadOfflineValue("draft"); first.text = "Changed";
  assert.deepEqual(await storage.loadOfflineValue("draft"), { text: "Saved" });
  assert.equal(database.state.closed, 1);
  assert.equal(storage.getOfflineStorageMode(), "persistent");
});
test("persistent writes commit a snapshot and close their connections", async () => {
  const database = fakeDatabase(); const storage = loadStorage(database);
  const value = { text: "Before" }; const save = storage.saveOfflineValue("draft", value); value.text = "After";
  await save;
  assert.equal(database.values.get("draft").value.text, "Before");
  assert.equal(database.state.closed, 1);
});
test("an aborted write retains input in memory and reports temporary storage", async () => {
  const database = fakeDatabase(new Map(), { abortWrites: true }); const storage = loadStorage(database);
  await storage.saveOfflineValue("draft", "New input");
  assert.equal(await storage.loadOfflineValue("draft"), "New input");
  assert.equal(storage.getOfflineStorageMode(), "memory"); assert.equal(database.state.closed, 1);
  assert.equal(database.values.has("draft"), false);
});
test("an aborted read settles and closes the database", async () => {
  const database = fakeDatabase(new Map(), { abortReads: true }); const storage = loadStorage(database);
  assert.equal(await storage.loadOfflineValue("draft"), null);
  assert.equal(storage.getOfflineStorageMode(), "memory"); assert.equal(database.state.closed, 1);
});
test("a failed deletion cannot restore the old draft within the same tab", async () => {
  const database = fakeDatabase(new Map([["draft", { key: "draft", value: "Old" }]]), { abortWrites: true });
  const storage = loadStorage(database); await storage.deleteOfflineValue("draft");
  assert.equal(await storage.loadOfflineValue("draft"), null);
  assert.equal(storage.getOfflineStorageMode(), "memory");
});
test("blocked opening falls back immediately and closes a late successful connection", async () => {
  const database = fakeDatabase(new Map(), { blocked: true }); const storage = loadStorage(database);
  await storage.saveOfflineValue("draft", "Text");
  assert.equal(storage.getOfflineStorageMode(), "memory"); database.state.finishLateOpen();
  assert.equal(database.state.closed, 1); assert.equal(await storage.loadOfflineValue("draft"), "Text");
});
test("write, delete and read wait for transactions in the requested order", { timeout: 1000 }, async () => {
  const database = fakeDatabase(new Map(), { holdWrites: true }); const storage = loadStorage(database);
  const save = storage.saveOfflineValue("draft", "Sent"); const remove = storage.deleteOfflineValue("draft");
  const read = storage.loadOfflineValue("draft");
  while (!database.state.pending.length) await new Promise(setImmediate);
  database.state.pending.shift()(); await save;
  while (!database.state.pending.length) await new Promise(setImmediate);
  database.state.pending.shift()(); await remove;
  assert.equal(await read, null); assert.equal(database.values.has("draft"), false);
});
test("file admission respects size and remaining quota, with unavailable estimates tolerated", async () => {
  assert.equal(await loadStorage(undefined).canStoreFile({ size: 21 * 1024 * 1024 }), false);
  const storage = loadStorage(undefined, { storage: { estimate: async () => ({ quota: 1000, usage: 900 }) } });
  assert.equal(await storage.canStoreFile({ size: 50 }), true);
  assert.equal(await storage.canStoreFile({ size: 90 }), false);
  const unavailable = loadStorage(undefined, { storage: { estimate: async () => { throw new Error("Unavailable"); } } });
  assert.equal(await unavailable.canStoreFile({ size: 100 }), true);
});
