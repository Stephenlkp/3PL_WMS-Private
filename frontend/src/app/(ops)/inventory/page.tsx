"use client";

import { useEffect, useState } from "react";
import { api, isManager } from "@/lib/api";
import { useUser } from "@/components/shell";
import { Banner, Button, Card, Field, PageHeader, Select } from "@/components/ui";
import type { Balance } from "@/lib/types";

export default function InventoryPage() {
  const user = useUser();
  const [view, setView] = useState("location");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Balance[]>([]);
  const [error, setError] = useState("");
  const [move, setMove] = useState({ barcode: "", from: "", to: "", quantity: "1" });

  function load(nextView = view, nextQ = q) {
    const params = new URLSearchParams({ view: nextView });
    if (nextQ) params.set("q", nextQ);
    api<Balance[]>(`/api/v1/inventory/balances?${params}`).then(setRows).catch((err) => setError(err.message));
  }

  useEffect(() => {
    if (user) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  async function submitMove() {
    setError("");
    try {
      await api("/api/v1/inventory/move", {
        method: "POST",
        body: JSON.stringify({
          barcode: move.barcode,
          from_location_code: move.from,
          to_location_code: move.to,
          quantity: Number(move.quantity),
        }),
      });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Move failed");
    }
  }

  return (
    <div>
      <PageHeader title="Inventory" lede="On hand is physical stock. Available is on hand minus reserved. Reserved is kept at SKU level until the order ships." />
      <form
        className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center"
        onSubmit={(event) => {
          event.preventDefault();
          load();
        }}
      >
        <Field className="sm:min-w-0 sm:flex-1" placeholder="SKU, barcode, name, location" value={q} onChange={(event) => setQ(event.target.value)} />
        <Select className="sm:w-40" value={view} onChange={(event) => { setView(event.target.value); load(event.target.value, q); }}>
          <option value="location">By location</option>
          <option value="sku">By SKU</option>
        </Select>
        <Button type="submit" className="sm:shrink-0">Search</Button>
      </form>
      {error && <div className="mb-4"><Banner>{error}</Banner></div>}
      <div className="overflow-auto rounded-2xl border border-line bg-card">
        <table className="min-w-full text-sm">
          <thead className="bg-paper text-left">
            <tr>
              {["Customer", "SKU", "Location", "At location", "On hand", "Reserved", "Available"].map((heading) => (
                <th key={heading} className="px-3 py-2 font-medium">{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.product_id}-${row.location_code}`} className="border-t border-line">
                <td className="px-3 py-2">{row.customer_name}</td>
                <td className="px-3 py-2 font-medium">{row.sku}<div className="text-xs text-ink/50">{row.product_name}</div></td>
                <td className="px-3 py-2 font-mono">{row.compact_location || row.location_code}</td>
                <td className="px-3 py-2 font-mono">{row.location_qty ?? "—"}</td>
                <td className="px-3 py-2 font-mono">{row.on_hand_qty}</td>
                <td className="px-3 py-2 font-mono">{row.reserved_qty}</td>
                <td className="px-3 py-2 font-mono">{row.available_qty}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {isManager(user?.role) && (
        <Card className="mt-6">
          <h2 className="font-semibold">Move stock</h2>
          <p className="mt-1 text-sm text-ink/60">Posts a MOVE out of the source and a MOVE into the destination. The total does not change.</p>
          <div className="mt-3 grid gap-2 md:grid-cols-4">
            <Field placeholder="Barcode" value={move.barcode} onChange={(event) => setMove({ ...move, barcode: event.target.value })} />
            <Field placeholder="From A-01-01" value={move.from} onChange={(event) => setMove({ ...move, from: event.target.value })} />
            <Field placeholder="To B-01-01" value={move.to} onChange={(event) => setMove({ ...move, to: event.target.value })} />
            <Field placeholder="Qty" value={move.quantity} onChange={(event) => setMove({ ...move, quantity: event.target.value })} />
          </div>
          <Button className="mt-3" onClick={submitMove}>Post move</Button>
        </Card>
      )}
    </div>
  );
}
