const DB_NAME = "botvpk-offline";
const STORE_NAME = "records";
const DB_VERSION = 1;

type StoredRecord<T> = { key: string; value: T; updatedAt: number };

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) database.createObjectStore(STORE_NAME, { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function saveOfflineValue<T>(key: string, value: T): Promise<void> {
  const database = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put({ key, value, updatedAt: Date.now() } satisfies StoredRecord<T>);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

export async function loadOfflineValue<T>(key: string): Promise<T | null> {
  const database = await openDatabase();
  const record = await new Promise<StoredRecord<T> | undefined>((resolve, reject) => {
    const request = database.transaction(STORE_NAME, "readonly").objectStore(STORE_NAME).get(key);
    request.onsuccess = () => resolve(request.result as StoredRecord<T> | undefined);
    request.onerror = () => reject(request.error);
  });
  database.close();
  return record?.value ?? null;
}

export async function deleteOfflineValue(key: string): Promise<void> {
  const database = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).delete(key);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

export async function canStoreFile(file: File): Promise<boolean> {
  if (file.size > 20 * 1024 * 1024) return false;
  const estimate = await navigator.storage?.estimate?.();
  if (!estimate?.quota || estimate.usage === undefined) return true;
  return file.size < (estimate.quota - estimate.usage) * 0.8;
}
