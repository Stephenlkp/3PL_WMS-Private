"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge, PageHeader, statusTone } from "@/components/ui";
import type { Order } from "@/lib/types";

export default function PackingQueuePage() {
  const [orders, setOrders] = useState<Order[]>([]);
  useEffect(() => {
    api<Order[]>("/api/v1/orders").then((rows) => setOrders(rows.filter((order) => ["PICKED", "PACKING", "READY_TO_SHIP"].includes(order.status)))).catch(() => setOrders([]));
  }, []);
  return (
    <div>
      <PageHeader title="Pack queue" lede="Scan every picked unit again. Packed quantities have to match picked quantities before the order can ship." />
      <div className="space-y-3">
        {orders.length === 0 && <p className="text-sm text-ink/60">Nothing is waiting at the pack station.</p>}
        {orders.map((order) => (
          <Link key={order.id} href={`/packing/${order.id}`} className="block rounded-2xl border border-line bg-card p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">{order.order_number}</p>
                <p className="text-sm text-ink/60">{order.customer_name} · {order.receiver_name}</p>
              </div>
              <Badge tone={statusTone(order.status)}>{order.status}</Badge>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
