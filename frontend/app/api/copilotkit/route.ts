import {
  CopilotRuntime,
  copilotRuntimeNextJSAppRouterEndpoint,
  ExperimentalEmptyAdapter,
} from "@copilotkit/runtime";
import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const runtime = new CopilotRuntime({
  remoteEndpoints: [{ url: `${BACKEND_URL}/copilotkit` }],
});

export const POST = async (req: NextRequest) => {
  const handler = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new ExperimentalEmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handler.handleRequest(req);
};
