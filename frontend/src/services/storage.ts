class InMemoryStorage {
  private store: Record<string, string> = {};

  getItem(key: string): string | null {
    return this.store[key] || null;
  }

  setItem(key: string, value: string): void {
    this.store[key] = value;
  }

  removeItem(key: string): void {
    delete this.store[key];
  }

  clear(): void {
    this.store = {};
  }
}

let storageEngine: {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};

try {
  const testKey = "__storage_test__";
  window.localStorage.setItem(testKey, testKey);
  window.localStorage.removeItem(testKey);
  storageEngine = window.localStorage;
} catch (e) {
  console.warn("Storage access blocked (sandbox restriction or cookies disabled). Falling back to in-memory store.");
  storageEngine = new InMemoryStorage();
}

export const safeStorage = {
  getItem(key: string): string | null {
    try {
      return storageEngine.getItem(key);
    } catch (e) {
      return null;
    }
  },
  setItem(key: string, value: string): void {
    try {
      storageEngine.setItem(key, value);
    } catch (e) {
      // Fail silently in sandboxed environments
    }
  }
};
