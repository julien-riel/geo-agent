import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string; name: string }> }
) {
  const { id, name } = await ctx.params;
  const r = await fetch(
    `${BACKEND_URL}/datasets/${encodeURIComponent(id)}/attributes/${encodeURIComponent(name)}/stats`
  );
  if (!r.ok) return new Response(await r.text(), { status: r.status });
  const body = await r.text();
  return new Response(body, {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
