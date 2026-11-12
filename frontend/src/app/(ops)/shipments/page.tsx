"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge, PageHeader, statusTone } from "@/components/ui";
import type { Shipment } from "@/lib/types";

export default function ShipmentsPage() {
  const [rows, setRows] = useState<Shipment[]>([]);
  useEffect(() => { api<Shipment[]>("/api/v1/shipments").then(setRows).catch(() => setRows([])); }, []);
  return (
    <div>
      <PageHeader title="Shipments" lede="Dispatch is the moment physical stock leaves. The airway bill stays attached to the shipment." />
      <div className="space-y-3">
        {rows.map((row) => (
          <Link key={row.id} href={`/packing/${row.order_id}`} className="block rounded-2xl border border-line bg-card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">{row.shipment_number}</p>
                <p className="text-sm text-ink/60">{row.order_number} · {row.customer_name} · {row.courier} {row.tracking_number || ""}</p>
              </div>
              <Badge tone={statusTone(row.status)}>{row.status}</Badge>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
