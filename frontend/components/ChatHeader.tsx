"use client";

import { useChatContext } from "@copilotkit/react-ui";

interface Props {
  onNewConversation: () => void;
}

export function ChatHeader({ onNewConversation }: Props) {
  const { labels, setOpen, icons } = useChatContext();
  return (
    <div className="copilotKitHeader">
      <div>{labels.title}</div>
      <div className="copilotKitHeaderControls" style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button
          onClick={onNewConversation}
          aria-label="Nouvelle conversation"
          title="Nouvelle conversation"
          style={{
            background: "transparent",
            border: "1px solid #ddd",
            borderRadius: 4,
            padding: "2px 8px",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          ↻ Nouveau
        </button>
        <button
          onClick={() => setOpen(false)}
          aria-label="Close"
          className="copilotKitHeaderCloseButton"
        >
          {icons.headerCloseIcon}
        </button>
      </div>
    </div>
  );
}
