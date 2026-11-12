"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Scanner } from "@/components/scanner";
import { Banner, Button, PageHeader } from "@/components/ui";
import type { PickList } from "@/lib/types";

export default function PickPage() {
  const params = useParams<{ id: string }>();
  const [pick, setPick] = useState<PickList | null>(null);
  const [error, setError] = useState("");
  const [good, setGood] = useState("");

  function load() {
    api<PickList>(`/api/v1/picklists/${params.id}`).then(setPick).catch((err) => setError(err.message));
  }
  useEffect(() => { if (params.id) load(); }, [params.id]);

  async function onScan(barcode: string) {
    setError("");
    setGood("");
    try {
      setPick(await api<PickList>(`/api/v1/picklists/${params.id}/scan`, { method: "POST", body: JSON.stringify({ barcode, quantity: 1 }) }));
      setGood(`Accepted ${barcode}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan rejected");
      return false;
    }
  }

  async function complete() {
    setError("");
    try {
      setPick(await api<PickList>(`/api/v1/picklists/${params.id}/complete`, { method: "POST" }));
      setGood("Pick complete. Send it to packing.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pick is still open");
    }
  }

  if (!pick) return <p className="text-sm text-ink/60">{error || "Loading pick…"}</p>;
  const done = pick.lines.every((line) => line.picked_qty === line.quantity);
  return (
    <div className="mx-auto max-w-xl">
      <PageHeader title={pick.order_number} lede={`${pick.customer_name} · ${pick.pick_number}`} />
      <ul className="mb-4 space-y-2">
        {pick.lines.map((line) => (
          <li key={line.id} className={`rounded-2xl border p-3 ${line.picked_qty === line.quantity ? "border-pine/40 bg-pine/5" : "border-line bg-card"}`}>
            <div className="flex items-center justify-between">
              <span className="font-mono text-lg">{line.compact_location}</span>
              <span className="font-mono">{line.picked_qty}/{line.quantity}</span>
            </div>
            <p className="mt-1 font-medium">{line.sku}</p>
            <p className="text-sm text-ink/60">{line.product_name}</p>
          </li>
        ))}
      </ul>
      {pick.status !== "PICKED" && <Scanner onScan={onScan} />}
      {error && <div className="mt-3"><Banner>{error}</Banner></div>}
      {good && <div className="mt-3"><Banner tone="good">{good}</Banner></div>}
      {pick.status !== "PICKED" && <Button className="mt-4 h-14 w-full text-base" disabled={!done} onClick={complete}>Complete pick</Button>}
    </div>
  );
}
