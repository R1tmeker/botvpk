const DB_NAME = "botvpk-offline";
const STORE_NAME = "records";
const DB_VERSION = 1;

type StoredRecord<T> = { key: string; value: T; updatedAt: number };
export type OfflineStorageMode = "persistent" | "memory";
const memory = new Map<string, StoredRecord<unknown> | null>();
const operations = new Map<string, Promise<unknown>>();
const listeners = new Set<() => void>();
let mode: OfflineStorageMode = "persistent";

export function getOfflineStorageMode(): OfflineStorageMode { return mode; }
export function subscribeOfflineStorage(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
function setMode(value: OfflineStorageMode) {
  if (mode === value) return;
  mode = value;
  for (const listener of listeners) listener();
}
function clone<T>(value: T): T {
  return typeof structuredClone === "function" ? structuredClone(value) : value;
}
function serialize<T>(key: string, operation: () => Promise<T>): Promise<T> {
  const previous = operations.get(key) ?? Promise.resolve();
  const pending = previous.catch(() => undefined).then(operation);
  operations.set(key, pending);
  void pending.finally(() => { if (operations.get(key) === pending) operations.delete(key); }).catch(() => undefined);
  return pending;
}
function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") { reject(new Error("IndexedDB is unavailable")); return; }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    let settled = false;
    const fail = (error: unknown) => { if (!settled) { settled = true; clearTimeout(timer); reject(error); } };
    const timer = setTimeout(() => fail(new Error("IndexedDB open timed out")), 2000);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) database.createObjectStore(STORE_NAME, { keyPath: "key" });
    };
    request.onsuccess = () => {
      if (settled) { request.result.close(); return; }
      settled = true; clearTimeout(timer); resolve(request.result);
    };
    request.onerror = () => fail(request.error);
    request.onblocked = () => fail(new Error("IndexedDB is blocked by another tab"));
  });
}
async function writeRecord(key: string, record: StoredRecord<unknown> | null): Promise<void> {
  let database: IDBDatabase | null = null;
  try {
    database = await openDatabase();
    await new Promise<void>((resolve, reject) => {
      const transaction = database!.transaction(STORE_NAME, "readwrite");
      const store = transaction.objectStore(STORE_NAME);
      if (record) store.put(record); else store.delete(key);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB transaction aborted"));
    });
    // A previous failure may still leave other keys only in memory, so keep the warning until reload.
  } catch {
    setMode("memory");
  } finally {
    database?.close();
  }
}
export function saveOfflineValue<T>(key: string, value: T): Promise<void> {
  const record: StoredRecord<T> = { key, value: clone(value), updatedAt: Date.now() };
  return serialize(key, async () => { memory.set(key, record); await writeRecord(key, record); });
}
export function loadOfflineValue<T>(key: string): Promise<T | null> {
  return serialize(key, async () => {
    if (memory.has(key)) return clone((memory.get(key)?.value as T | undefined) ?? null);
    let database: IDBDatabase | null = null;
    try {
      database = await openDatabase();
      const record = await new Promise<StoredRecord<T> | undefined>((resolve, reject) => {
        const transaction = database!.transaction(STORE_NAME, "readonly");
        const request = transaction.objectStore(STORE_NAME).get(key);
        request.onsuccess = () => resolve(request.result as StoredRecord<T> | undefined);
        request.onerror = () => reject(request.error);
        transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB transaction aborted"));
      });
      memory.set(key, record ?? null);
      return record ? clone(record.value) : null;
    } catch {
      setMode("memory");
      return null;
    } finally {
      database?.close();
    }
  });
}
export function deleteOfflineValue(key: string): Promise<void> {
  return serialize(key, async () => { memory.set(key, null); await writeRecord(key, null); });
}
export async function canStoreFile(file: File): Promise<boolean> {
  if (file.size > 20 * 1024 * 1024) return false;
  try {
    const estimate = typeof navigator !== "undefined" ? await navigator.storage?.estimate?.() : null;
    if (!estimate?.quota || estimate.usage === undefined) return true;
    return file.size < Math.max(0, estimate.quota - estimate.usage) * 0.8;
  } catch {
    return true;
  }
}
