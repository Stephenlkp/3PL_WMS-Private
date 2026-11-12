"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, isManager } from "@/lib/api";
import { useUser } from "@/components/shell";
import { Badge, PageHeader, statusTone } from "@/components/ui";
import type { Order } from "@/lib/types";

export default function OrdersPage() {
  const user = useUser();
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Order[]>("/api/v1/orders").then(setOrders).catch((err) => setError(err.message));
  }, []);
  return (
    <div>
      <PageHeader
        title="Orders"
        lede="A new order reserves stock. Physical stock stays put until dispatch."
        action={user && (isManager(user.role) || user.role === "customer") ? <Link href="/orders/new" className="inline-flex h-11 items-center rounded-xl bg-ink px-4 text-sm text-paper">New order</Link> : undefined}
      />
      {error && <p className="text-brick">{error}</p>}
      <div className="space-y-3">
        {orders.map((order) => (
          <Link key={order.id} href={`/orders/${order.id}`} className="block rounded-2xl border border-line bg-card p-4 shadow-card">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="font-semibold">{order.order_number}</p>
                <p className="text-sm text-ink/60">{order.customer_name} · {order.receiver_name} · {order.courier}</p>
              </div>
              <Badge tone={statusTone(order.status)}>{order.status}</Badge>
            </div>
            <p className="mt-2 text-sm">{order.items.map((item) => `${item.sku} × ${item.quantity}`).join(" · ")}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
