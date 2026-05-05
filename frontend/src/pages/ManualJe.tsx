import { ChangeEvent, FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError, ManualJeLine, api } from "../api/client";

interface FormLine {
  account_code: string;
  side: "Dr" | "Cr";
  amount: string;
  sub_ledger_keys: string;
  dimensions: string;
}

export function ManualJe() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [narration, setNarration] = useState("");
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [attachmentId, setAttachmentId] = useState<number | null>(null);
  const [attachmentName, setAttachmentName] = useState<string | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [reverseJeId, setReverseJeId] = useState("");
  const [reverseNarration, setReverseNarration] = useState("");
  const [lines, setLines] = useState<FormLine[]>([
    { account_code: "", side: "Dr", amount: "", sub_ledger_keys: "", dimensions: "" },
    { account_code: "", side: "Cr", amount: "", sub_ledger_keys: "", dimensions: "" },
  ]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ je_id: number; total: string } | null>(null);
  const [reverseSuccess, setReverseSuccess] = useState<number | null>(null);

  const uploadFile = useMutation({
    mutationFn: (f: File) => api.uploadFile(f),
    onSuccess: (r) => { setAttachmentId(r.attachment_id); setAttachmentName(attachmentFile?.name ?? null); },
    onError: (e) => setError(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  const post = useMutation({
    mutationFn: (payload: Parameters<typeof api.postManualJe>[0]) => api.postManualJe(payload),
    onSuccess: (resp) => { setSuccess({ je_id: resp.je_id, total: resp.total_aed }); setError(null); },
    onError: (e: unknown) => {
      setError(e instanceof ApiError ? JSON.stringify(e.body) : String(e));
      setSuccess(null);
    },
  });

  const reverse = useMutation({
    mutationFn: () =>
      api.reverseJe(Number(reverseJeId), reverseNarration || `Reversal of JE #${reverseJeId}`),
    onSuccess: (r) => { setReverseSuccess(r.je_id); setError(null); },
    onError: (e: unknown) => setError(e instanceof ApiError ? JSON.stringify(e.body) : String(e)),
  });

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setAttachmentFile(f);
    setAttachmentId(null);
    setAttachmentName(null);
    uploadFile.mutate(f);
  };

  const updateLine = (idx: number, patch: Partial<FormLine>) =>
    setLines((cur) => cur.map((l, i) => (i === idx ? { ...l, ...patch } : l)));

  const addLine = () =>
    setLines((cur) => [
      ...cur,
      { account_code: "", side: "Dr", amount: "", sub_ledger_keys: "", dimensions: "" },
    ]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      const payloadLines: ManualJeLine[] = lines.map((l) => ({
        account_code: l.account_code.trim(),
        debit_aed: l.side === "Dr" ? l.amount : "0",
        credit_aed: l.side === "Cr" ? l.amount : "0",
        sub_ledger_keys: l.sub_ledger_keys.trim() ? JSON.parse(l.sub_ledger_keys) : {},
        dimensions: l.dimensions.trim() ? JSON.parse(l.dimensions) : {},
      }));
      post.mutate({
        date,
        narration,
        attachment_id: attachmentId,
        attachment_override_reason: overrideReason || null,
        lines: payloadLines,
      });
    } catch (err) {
      setError(`bad JSON in keys/dimensions: ${err}`);
    }
  };

  const total = lines.reduce(
    (acc, l) => {
      const v = Number(l.amount || 0);
      return l.side === "Dr" ? { dr: acc.dr + v, cr: acc.cr } : { dr: acc.dr, cr: acc.cr + v };
    },
    { dr: 0, cr: 0 },
  );

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Post manual journal entry</h2>

      {/* Reversal section */}
      <div className="card space-y-3">
        <h3 className="text-sm font-semibold">Reverse an existing JE</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">JE ID to reverse</label>
            <input
              className="input font-mono"
              placeholder="123"
              value={reverseJeId}
              onChange={(e) => setReverseJeId(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Reversal narration (optional)</label>
            <input
              className="input"
              value={reverseNarration}
              onChange={(e) => setReverseNarration(e.target.value)}
            />
          </div>
        </div>
        {reverseSuccess && (
          <div className="text-sm text-green-700">Reversal posted as JE #{reverseSuccess}</div>
        )}
        <button
          className="btn"
          disabled={!reverseJeId || reverse.isPending}
          onClick={() => reverse.mutate()}
        >
          {reverse.isPending ? "Reversing…" : "Post Reversal"}
        </button>
      </div>

      {/* New JE section */}
      <form onSubmit={onSubmit} className="card">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-xs font-medium mb-1">Date</label>
            <input className="input" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Narration (≥ 10 chars)</label>
            <input className="input" value={narration} onChange={(e) => setNarration(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">
              Attachment (PDF / image / CSV — required for manual JEs &gt; AED 50 000)
            </label>
            <input type="file" className="input" onChange={onFileChange} />
            {uploadFile.isPending && <span className="text-xs text-ink-700 mt-1">Uploading…</span>}
            {attachmentName && attachmentId && (
              <span className="text-xs text-green-700 mt-1">
                Attached: {attachmentName} (id={attachmentId})
              </span>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">
              Override reason (≥ 30 chars; alternative to attachment for &gt;50 000)
            </label>
            <input
              className="input"
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
            />
          </div>
        </div>

        <table className="min-w-full mb-3">
          <thead>
            <tr>
              <th className="table-head">Account</th>
              <th className="table-head">Side</th>
              <th className="table-head">Amount</th>
              <th className="table-head">Sub-ledger keys (JSON)</th>
              <th className="table-head">Dimensions (JSON)</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={i}>
                <td className="table-cell">
                  <input
                    className="input"
                    value={l.account_code}
                    onChange={(e) => updateLine(i, { account_code: e.target.value })}
                  />
                </td>
                <td className="table-cell">
                  <select
                    className="input"
                    value={l.side}
                    onChange={(e) => updateLine(i, { side: e.target.value as "Dr" | "Cr" })}
                  >
                    <option value="Dr">Dr</option>
                    <option value="Cr">Cr</option>
                  </select>
                </td>
                <td className="table-cell">
                  <input
                    className="input money"
                    value={l.amount}
                    onChange={(e) => updateLine(i, { amount: e.target.value })}
                  />
                </td>
                <td className="table-cell">
                  <input
                    className="input font-mono text-xs"
                    placeholder='{"student_id": 1}'
                    value={l.sub_ledger_keys}
                    onChange={(e) => updateLine(i, { sub_ledger_keys: e.target.value })}
                  />
                </td>
                <td className="table-cell">
                  <input
                    className="input font-mono text-xs"
                    placeholder='{"enrollment_id": 42}'
                    value={l.dimensions}
                    onChange={(e) => updateLine(i, { dimensions: e.target.value })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="flex items-center justify-between">
          <button type="button" onClick={addLine} className="btn-ghost">Add line</button>
          <div className="text-sm">
            Dr <span className="font-mono">{total.dr.toFixed(2)}</span>
            <span className="text-ink-200 mx-1">·</span>
            Cr <span className="font-mono">{total.cr.toFixed(2)}</span>
            <span className="text-ink-200 mx-1">·</span>
            <span className={total.dr === total.cr ? "text-accent-600" : "text-red-600"}>
              {total.dr === total.cr ? "balanced" : "unbalanced"}
            </span>
          </div>
        </div>

        {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
        {success && (
          <div className="text-sm text-accent-600 mt-3">
            Posted JE #{success.je_id} (total {success.total} AED)
          </div>
        )}

        <button className="btn mt-4" disabled={post.isPending}>
          {post.isPending ? "Posting…" : "Post journal entry"}
        </button>
      </form>
    </div>
  );
}
