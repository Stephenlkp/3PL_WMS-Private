"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { Field, PageHeader } from "@/components/ui";
import type { SearchHit } from "@/lib/types";

export default function SearchPage() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const result = await api<{ hits: SearchHit[] }>(`/api/v1/search?q=${encodeURIComponent(q)}`);
      setHits(result.hits);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  return (
    <div>
      <PageHeader title="Search" lede="SKU, barcode, product name, location, tracking number, or order number." />
      <form onSubmit={submit} className="mb-4 flex gap-2">
        <Field value={q} onChange={(event) => setQ(event.target.value)} placeholder="MRO400EU" />
        <button className="h-11 rounded-xl bg-ink px-4 text-sm text-paper">Search</button>
      </form>
      {error && <p className="text-sm text-brick">{error}</p>}
      <div className="space-y-2">
        {hits.map((hit, index) => (
          <article key={`${hit.kind}-${hit.label}-${index}`} className="rounded-xl border border-line bg-card px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-ink/40">{hit.kind}</p>
            <p className="font-semibold">{hit.label}</p>
            <p className="text-sm text-ink/70">{hit.detail} {hit.location_code ? `· ${hit.location_code}` : ""} {hit.tracking_number ? `· ${hit.tracking_number}` : ""}</p>
            {hit.on_hand_qty !== null && (
              <p className="mt-1 font-mono text-sm">On hand {hit.on_hand_qty} · Reserved {hit.reserved_qty} · Available {hit.available_qty}</p>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
