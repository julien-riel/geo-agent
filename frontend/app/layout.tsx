"use client";

import { CopilotKit } from "@copilotkit/react-core";
import "@copilotkit/react-ui/styles.css";
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // The /api/copilotkit Next.js route is not a redundant proxy — it is the
  // CopilotKit Runtime adapter that translates CopilotKit's chat protocol
  // into AG-UI requests for the FastAPI /agents/geo-agent endpoint.
  // selfManagedAgents was investigated as a way to talk straight to FastAPI
  // from the browser, but CopilotKit React 1.5 still routes agent traffic
  // through runtimeUrl regardless. See docs/ARCHITECTURE.md for details.
  return (
    <html lang="fr">
      <body>
        <CopilotKit runtimeUrl="/api/copilotkit" agent="geo-agent">
          {children}
        </CopilotKit>
      </body>
    </html>
  );
}
