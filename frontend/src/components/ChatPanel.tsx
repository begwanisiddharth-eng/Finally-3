"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Panel from "./Panel";
import { api, ApiError } from "@/lib/api";
import { useAppData } from "@/providers/AppDataProvider";
import type { ChatAction, ChatMessage } from "@/lib/types";

export default function ChatPanel() {
  const { refreshAfterTrade } = useAppData();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const wasPending = useRef(false);

  useEffect(() => {
    api.getChatHistory().then(setMessages).catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo?.(0, scrollRef.current.scrollHeight);
  }, [messages, pending]);

  // Return focus to the input once a response completes (input was re-enabled).
  useEffect(() => {
    if (wasPending.current && !pending) inputRef.current?.focus();
    wasPending.current = pending;
  }, [pending]);

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || pending) return;
    setError("");
    setInput("");
    const now = new Date().toISOString();
    setMessages((m) => [...m, { role: "user", content: text, actions: null, created_at: now }]);
    setPending(true);
    try {
      const res = await api.chat(text);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: res.message, actions: res.actions, created_at: new Date().toISOString() },
      ]);
      if (res.actions.length) await refreshAfterTrade();
    } catch (err) {
      // 502/upstream: not persisted. Drop the optimistic user line, keep the text.
      setMessages((m) => m.slice(0, -1));
      setInput(text);
      setError(err instanceof ApiError ? err.message : "Chat failed");
    } finally {
      setPending(false);
    }
  };

  return (
    <Panel title="AI Assistant" className="h-full">
      <div className="flex h-full flex-col">
        <div ref={scrollRef} className="flex-1 space-y-3 overflow-auto p-3">
          {messages.length === 0 && !pending && (
            <p className="text-sm text-fg-muted">
              Ask about your portfolio, or tell me to buy, sell, or manage your watchlist.
            </p>
          )}
          {messages.map((m, i) => (
            <Message key={i} message={m} />
          ))}
          {pending && <p className="text-sm text-fg-muted">Thinking…</p>}
          {error && <p className="text-sm text-down">{error}</p>}
        </div>
        <form onSubmit={send} className="flex gap-2 border-t border-border-soft p-2">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={pending}
            placeholder="Message FinAlly…"
            className="min-w-0 flex-1 rounded border border-border bg-bg px-2 py-1.5 text-sm outline-none focus:border-blue disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={pending}
            className="rounded bg-purple px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </Panel>
  );
}

function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={isUser ? "text-right" : "text-left"}>
      <div
        className={`inline-block max-w-[90%] rounded-md px-3 py-2 text-sm ${
          isUser ? "bg-blue/20 text-fg" : "bg-panel-alt text-fg"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {message.actions && message.actions.length > 0 && (
          <ul className="mt-2 space-y-1 border-t border-border-soft pt-2 text-xs">
            {message.actions.map((a, i) => (
              <ActionLine key={i} action={a} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ActionLine({ action }: { action: ChatAction }) {
  const ok = action.status === "executed";
  const label =
    action.type === "trade"
      ? `${action.side ?? ""} ${action.quantity ?? ""} ${action.ticker}`.trim()
      : `${action.action ?? ""} ${action.ticker}`.trim();
  return (
    <li className={ok ? "text-up" : "text-down"}>
      {ok ? "✓" : "✗"} {label}
      {!ok && action.error ? ` — ${action.error}` : ""}
    </li>
  );
}
