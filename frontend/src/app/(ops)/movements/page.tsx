"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/ui";
import type { Movement } from "@/lib/types";

export default function MovementsPage() {
  const [rows, setRows] = useState<Movement[]>([]);
  useEffect(() => { api<Movement[]>("/api/v1/inventory/transactions?limit=100").then(setRows).catch(() => setRows([])); }, []);
  return (
    <div>
      <PageHeader title="Stock movements" lede="Every row is a ledger posting. Positive quantities add, negative quantities remove." />
      <div className="overflow-auto rounded-2xl border border-line bg-card">
        <table className="min-w-full text-sm">
          <thead className="bg-paper text-left">
            <tr>{["When", "SKU", "Type", "Qty", "Location", "Reference"].map((heading) => <th key={heading} className="px-3 py-2">{heading}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-line">
                <td className="px-3 py-2 whitespace-nowrap">{new Date(row.created_at).toLocaleString()}</td>
                <td className="px-3 py-2">{row.sku}</td>
                <td className="px-3 py-2">{row.transaction_type}</td>
                <td className="px-3 py-2 font-mono">{row.quantity}</td>
                <td className="px-3 py-2 font-mono">{row.location_code || "—"}</td>
                <td className="px-3 py-2 font-mono">{row.reference_no}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
