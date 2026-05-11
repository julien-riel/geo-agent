import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { LangGraphHttpAgent } from "@copilotkit/runtime/langgraph";
import { NextRequest } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const runtime = new CopilotRuntime({
  agents: {
    "geo-agent": new LangGraphHttpAgent({
      url: `${BACKEND_URL}/agents/geo-agent`,
    }),
  },
});

export const POST = async (req: NextRequest) => {
  const handler = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter: new ExperimentalEmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handler.handleRequest(req);
};
