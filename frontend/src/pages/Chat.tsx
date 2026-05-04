import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ChatMessagePayload } from "../api/client";

export function Chat() {
  const qc = useQueryClient();
  const [sid, setSid] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const tools = useQuery({ queryKey: ["chat", "tools"], queryFn: () => api.chatTools() });

  const createSession = useMutation({
    mutationFn: () => api.chatCreateSession(),
    onSuccess: ({ id }) => setSid(id),
  });

  // Auto-create a session on first mount.
  useEffect(() => {
    if (!sid && !createSession.isPending) createSession.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const session = useQuery({
    queryKey: ["chat", "session", sid],
    queryFn: () => (sid ? api.chatGetSession(sid) : Promise.reject("no sid")),
    enabled: !!sid,
  });

  const send = useMutation({
    mutationFn: (m: string) => api.chatPost(sid as string, m),
    onSuccess: () => {
      setDraft("");
      qc.invalidateQueries({ queryKey: ["chat", "session", sid] });
    },
  });

  // Scroll to the bottom whenever new messages land.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [session.data?.messages.length]);

  const messages = useMemo(() => session.data?.messages ?? [], [session.data]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (draft.trim() && sid) send.mutate(draft.trim());
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_18rem] gap-4">
      <div className="card p-0 flex flex-col h-[70vh]">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-sm text-ink-700">
              Ask the CFO assistant a question — e.g. "What was net profit in 2026-04?",
              "Is period 2026-03 closed?", "Any sanctions waiting on me?"
            </div>
          )}
          {messages.map((m, i) => (
            <MessageBubble key={i} m={m} />
          ))}
          {send.isPending && <div className="text-xs text-ink-700">Thinking…</div>}
        </div>
        <form onSubmit={onSubmit} className="border-t border-ink-200 p-3 flex gap-2">
          <input
            className="input flex-1"
            placeholder={sid ? "Ask the GL…" : "Connecting…"}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            disabled={!sid || send.isPending}
          />
          <button className="btn" disabled={!sid || !draft.trim() || send.isPending}>
            Send
          </button>
        </form>
      </div>

      <aside className="card text-xs space-y-2">
        <h3 className="text-sm font-semibold">Available tools</h3>
        <p className="text-ink-700">
          Read-only — the chat agent cannot modify the books.
        </p>
        <ul className="space-y-1">
          {(tools.data ?? []).map((t) => (
            <li key={t.name}>
              <code className="font-mono text-[11px]">{t.name}</code>
              <div className="text-ink-700">{t.description}</div>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

function MessageBubble({ m }: { m: ChatMessagePayload }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-accent-500 text-white rounded-2xl rounded-br-sm px-3 py-2 max-w-[80%]">
          {m.content}
        </div>
      </div>
    );
  }
  if (m.role === "assistant") {
    return (
      <div className="flex justify-start">
        <div className="bg-ink-100 rounded-2xl rounded-bl-sm px-3 py-2 max-w-[80%] whitespace-pre-wrap">
          {m.content}
        </div>
      </div>
    );
  }
  if (m.role === "tool") {
    return (
      <details className="text-[11px] font-mono text-ink-700 bg-ink-50 border border-ink-200 rounded p-2">
        <summary>
          ▸ <span className="font-semibold">{m.tool_name}</span>{" "}
          {m.tool_input ? <span>· {JSON.stringify(m.tool_input)}</span> : null}
        </summary>
        <pre className="whitespace-pre-wrap mt-2">{m.content}</pre>
      </details>
    );
  }
  return null;
}
