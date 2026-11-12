"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, fileUrl, isStaff } from "@/lib/api";
import { useUser } from "@/components/shell";
import { Badge, Banner, Button, PageHeader, statusTone } from "@/components/ui";
import type { Order } from "@/lib/types";

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const user = useUser();
  const [order, setOrder] = useState<Order | null>(null);
  const [error, setError] = useState("");

  function load() {
    api<Order>(`/api/v1/orders/${params.id}`).then(setOrder).catch((err) => setError(err.message));
  }
  useEffect(() => { if (params.id) load(); }, [params.id]);

  async function upload(file: File) {
    const body = new FormData();
    body.append("file", file);
    try {
      setOrder(await api<Order>(`/api/v1/orders/${params.id}/airway-bill`, { method: "POST", body }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  async function run(path: string) {
    setError("");
    try {
      await api(path, { method: "POST" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    }
  }

  if (!order) return <p className="text-sm text-ink/60">{error || "Loading order…"}</p>;
  return (
    <div>
      <PageHeader title={order.order_number} lede={`${order.customer_name} · ${order.receiver_name} · ${order.receiver_phone}`} action={<Badge tone={statusTone(order.status)}>{order.status}</Badge>} />
      <p className="mb-4 text-sm">{order.receiver_address}<br />{order.courier} {order.tracking_number || ""}</p>
      {error && <div className="mb-4"><Banner>{error}</Banner></div>}
      <div className="overflow-hidden rounded-2xl border border-line bg-card">
        <table className="min-w-full text-sm">
          <thead className="bg-paper text-left"><tr>{["SKU", "Order", "Picked", "Packed"].map((heading) => <th key={heading} className="px-3 py-2">{heading}</th>)}</tr></thead>
          <tbody>
            {order.items.map((item) => (
              <tr key={item.id} className="border-t border-line">
                <td className="px-3 py-2">{item.sku}<div className="text-xs text-ink/50">{item.product_name}</div></td>
                <td className="px-3 py-2 font-mono">{item.quantity}</td>
                <td className="px-3 py-2 font-mono">{item.picked_qty}</td>
                <td className="px-3 py-2 font-mono">{item.packed_qty}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {isStaff(user?.role) && order.status === "PENDING" && <Button onClick={() => run(`/api/v1/orders/${order.id}/picklist`)}>Generate pick list</Button>}
        {order.picklist_id && <Link className="inline-flex h-11 items-center rounded-xl border border-line bg-white px-4 text-sm" href={`/picking/${order.picklist_id}`}>Open pick</Link>}
        {["PICKED", "PACKING", "READY_TO_SHIP"].includes(order.status) && <Link className="inline-flex h-11 items-center rounded-xl border border-line bg-white px-4 text-sm" href={`/packing/${order.id}`}>Open pack</Link>}
        {order.status === "PENDING" && <Button variant="danger" onClick={() => run(`/api/v1/orders/${order.id}/cancel`)}>Cancel and release</Button>}
      </div>
      <label className="mt-6 block text-sm">
        Airway bill (JPEG, PNG, or PDF)
        <input className="mt-2 block" type="file" accept="image/jpeg,image/png,application/pdf" onChange={(event) => { const file = event.target.files?.[0]; if (file) upload(file); }} />
      </label>
      {order.airway_bill_file_id && (
        <div className="mt-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={fileUrl(order.airway_bill_file_id)} alt="Airway bill" className="max-h-80 rounded-xl border border-line" />
          <a className="mt-2 inline-block text-sm text-tide" href={fileUrl(order.airway_bill_file_id)} target="_blank">Download airway bill</a>
        </div>
      )}
    </div>
  );
}
