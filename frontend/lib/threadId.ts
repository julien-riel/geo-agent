const KEY = "geo-agent-thread-id";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

let inMemoryFallback: string | null = null;

function safeGetItem(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return inMemoryFallback;
  }
}

function safeSetItem(value: string): void {
  try {
    sessionStorage.setItem(KEY, value);
  } catch {
    inMemoryFallback = value;
    console.warn("threadId: sessionStorage unavailable, using in-memory fallback");
  }
}

function generate(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function getOrCreateThreadId(): string {
  const existing = safeGetItem();
  if (existing && UUID_RE.test(existing)) return existing;
  const fresh = generate();
  safeSetItem(fresh);
  return fresh;
}

export function resetThreadId(): string {
  const fresh = generate();
  safeSetItem(fresh);
  return fresh;
}
