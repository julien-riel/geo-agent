import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const r = await fetch(`${BACKEND_URL}/datasets/${id}/geojson`);
  if (!r.ok) return new Response("not found", { status: 404 });
  const body = await r.text();
  return new Response(body, {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
