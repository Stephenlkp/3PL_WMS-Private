"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useUser } from "@/components/shell";
import { Card, PageHeader } from "@/components/ui";

type Low = { sku: string; product_name: string; available_qty: number; reorder_point: number; customer_name: string };
type Fast = { sku: string; product_name: string; outbound_qty: number };
type Dead = { sku: string; product_name: string; on_hand_qty: number; customer_name: string };

export default function DashboardPage() {
  const user = useUser();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    const path = user.role === "customer" ? "/api/v1/reports/customer-dashboard" : "/api/v1/reports/warehouse-dashboard";
    api<Record<string, unknown>>(path).then(setData).catch((err) => setError(err.message));
  }, [user]);

  if (error) return <p className="text-brick">{error}</p>;
  if (!data) return <p className="text-sm text-ink/60">Loading the floor…</p>;

  const customer = user?.role === "customer";
  const stats = customer
    ? [
        ["SKUs on hand", data.total_sku],
        ["Physical stock", data.total_stock],
        ["Reserved", data.reserved_stock],
        ["Available", data.available_stock],
        ["Open orders", data.open_orders],
        ["Shipped today", data.shipments_today],
      ]
    : [
        ["SKUs on hand", data.total_sku],
        ["Physical stock", data.total_stock],
        ["Awaiting pick", data.orders_awaiting_picking],
        ["Awaiting pack", data.orders_awaiting_packing],
        ["Ready to ship", data.ready_to_ship],
        ["Shipped today", data.shipments_today],
      ];
  const low = (data.low_inventory as Low[]) || [];
  const fast = (data.fast_moving as Fast[]) || [];
  const dead = (data.dead_stock as Dead[]) || [];

  return (
    <div>
      <PageHeader title={customer ? `${data.customer_name} inventory` : "Floor today"} lede="Quantities come from the ledger. Nothing on this page is an editable balance." />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {stats.map(([label, value]) => (
          <Card key={String(label)}>
            <p className="text-sm text-ink/60">{label as string}</p>
            <p className="mt-2 text-3xl font-semibold">{String(value)}</p>
          </Card>
        ))}
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card>
          <h2 className="font-semibold">Low inventory</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {low.length === 0 && <li className="text-ink/50">Reorder points are clear.</li>}
            {low.map((row) => (
              <li key={row.sku} className="flex justify-between gap-3">
                <span>{row.sku}</span>
                <span className="font-mono">{row.available_qty}/{row.reorder_point}</span>
              </li>
            ))}
          </ul>
        </Card>
        {!customer && (
          <>
            <Card>
              <h2 className="font-semibold">Fast moving, 30 days</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {fast.length === 0 && <li className="text-ink/50">No outbound units in the window.</li>}
                {fast.map((row) => (
                  <li key={row.sku} className="flex justify-between"><span>{row.sku}</span><span className="font-mono">{row.outbound_qty}</span></li>
                ))}
              </ul>
            </Card>
            <Card>
              <h2 className="font-semibold">Dead stock, 90 days</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {dead.length === 0 && <li className="text-ink/50">Every on-hand SKU has moved recently.</li>}
                {dead.map((row) => (
                  <li key={row.sku} className="flex justify-between"><span>{row.sku}</span><span className="font-mono">{row.on_hand_qty}</span></li>
                ))}
              </ul>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
