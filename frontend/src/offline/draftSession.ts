export type DraftStore<T> = {
  load: (key: string) => Promise<T | null>;
  save: (key: string, value: T) => Promise<void>;
  remove: (key: string) => Promise<void>;
};
export type DraftSnapshot<T> = { value: T; ready: boolean; restored: boolean; dirty: boolean; saving: boolean; savedAt: number | null; revision: number };

export class DraftSession<T> {
  private snapshot: DraftSnapshot<T>;
  private listeners = new Set<(snapshot: DraftSnapshot<T>) => void>();
  private closed = false;
  private flushing: { revision: number; promise: Promise<void> } | null = null;
  private pendingSaves = 0;

  constructor(readonly key: string, private initial: T, private store: DraftStore<T>) {
    this.snapshot = { value: initial, ready: false, restored: false, dirty: false, saving: false, savedAt: null, revision: 0 };
  }
  getSnapshot(): DraftSnapshot<T> { return this.snapshot; }
  subscribe(listener: (snapshot: DraftSnapshot<T>) => void): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }
  private emit(patch: Partial<DraftSnapshot<T>>) {
    this.snapshot = { ...this.snapshot, ...patch };
    if (!this.closed) for (const listener of this.listeners) listener(this.snapshot);
  }
  async restore(): Promise<void> {
    const revision = this.snapshot.revision;
    const saved = await this.store.load(this.key);
    if (this.closed) {
      if (this.snapshot.dirty) { this.emit({ ready: true }); await this.flush(); }
      return;
    }
    const unchanged = this.snapshot.revision === revision && !this.snapshot.dirty;
    this.emit({ value: unchanged && saved !== null ? saved : this.snapshot.value, ready: true, restored: unchanged && saved !== null });
  }
  update(next: T | ((previous: T) => T)): void {
    if (this.closed) return;
    const value = typeof next === "function" ? (next as (previous: T) => T)(this.snapshot.value) : next;
    this.emit({ value, dirty: true, revision: this.snapshot.revision + 1 });
  }
  flush(): Promise<void> {
    if (!this.snapshot.ready || !this.snapshot.dirty) return Promise.resolve();
    const { revision, value } = this.snapshot;
    if (this.flushing?.revision === revision) return this.flushing.promise;
    this.pendingSaves += 1;
    this.emit({ saving: true });
    const promise = this.store.save(this.key, value).then(() => {
      if (this.snapshot.revision === revision) this.emit({ savedAt: Date.now(), dirty: false });
    }).finally(() => {
      this.pendingSaves -= 1;
      this.emit({ saving: this.pendingSaves > 0 });
      if (this.flushing?.revision === revision) this.flushing = null;
    });
    this.flushing = { revision, promise };
    return promise;
  }
  async clear(): Promise<void> {
    this.emit({ value: this.initial, dirty: false, restored: false, saving: false, savedAt: null, revision: this.snapshot.revision + 1, ready: true });
    await this.store.remove(this.key);
  }
  close(): void {
    this.closed = true;
    this.listeners.clear();
    void this.flush();
  }
}
