"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge, PageHeader, statusTone } from "@/components/ui";
import type { PickList } from "@/lib/types";

export default function PickingQueuePage() {
  const [rows, setRows] = useState<PickList[]>([]);
  useEffect(() => { api<PickList[]>("/api/v1/picklists").then(setRows).catch(() => setRows([])); }, []);
  return (
    <div>
      <PageHeader title="Pick queue" lede="Route is zone, then rack, then level. Scan the barcode on the next screen before the line can complete." />
      <div className="space-y-3">
        {rows.length === 0 && <p className="text-sm text-ink/60">The pick queue is clear.</p>}
        {rows.map((pick) => (
          <Link key={pick.id} href={`/picking/${pick.id}`} className="block rounded-2xl border border-line bg-card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">{pick.order_number}</p>
                <p className="text-sm text-ink/60">{pick.customer_name}</p>
              </div>
              <Badge tone={statusTone(pick.status)}>{pick.status}</Badge>
            </div>
            <ul className="mt-3 space-y-1 font-mono text-sm">
              {pick.lines.map((line) => <li key={line.id}>{line.sku} × {line.quantity} · {line.location_code}</li>)}
            </ul>
          </Link>
        ))}
      </div>
    </div>
  );
}
