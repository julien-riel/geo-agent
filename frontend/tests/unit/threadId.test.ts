import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { getOrCreateThreadId, resetThreadId } from "@/lib/threadId";

const KEY = "geo-agent-thread-id";

beforeEach(() => sessionStorage.clear());
afterEach(() => sessionStorage.clear());

describe("threadId", () => {
  it("returns the same id on repeat calls within a session", () => {
    const a = getOrCreateThreadId();
    const b = getOrCreateThreadId();
    expect(a).toBe(b);
    expect(a).toMatch(/^[0-9a-f-]{36}$/i);
  });

  it("generates a new id after sessionStorage is cleared", () => {
    const a = getOrCreateThreadId();
    sessionStorage.clear();
    const b = getOrCreateThreadId();
    expect(a).not.toBe(b);
  });

  it("resetThreadId mints a new id and overwrites storage", () => {
    const a = getOrCreateThreadId();
    const b = resetThreadId();
    expect(b).not.toBe(a);
    expect(sessionStorage.getItem(KEY)).toBe(b);
  });

  it("treats an obviously malformed stored value as missing", () => {
    sessionStorage.setItem(KEY, "not-a-uuid");
    const id = getOrCreateThreadId();
    expect(id).toMatch(/^[0-9a-f-]{36}$/i);
    expect(sessionStorage.getItem(KEY)).toBe(id);
  });
});
