"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, fileUrl } from "@/lib/api";
import { Scanner } from "@/components/scanner";
import { Banner, Button, PageHeader } from "@/components/ui";
import type { Order, Shipment } from "@/lib/types";

export default function PackStationPage() {
  const params = useParams<{ id: string }>();
  const [order, setOrder] = useState<Order | null>(null);
  const [shipment, setShipment] = useState<Shipment | null>(null);
  const [error, setError] = useState("");
  const [good, setGood] = useState("");

  function load() {
    api<Order>(`/api/v1/orders/${params.id}`).then(setOrder).catch((err) => setError(err.message));
  }
  useEffect(() => { if (params.id) load(); }, [params.id]);

  async function onScan(barcode: string) {
    setError("");
    try {
      setOrder(await api<Order>(`/api/v1/orders/${params.id}/pack-scan`, { method: "POST", body: JSON.stringify({ barcode, quantity: 1 }) }));
      setGood(`Packed ${barcode}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan rejected");
      return false;
    }
  }

  async function finish() {
    setError("");
    try {
      setShipment(await api<Shipment>(`/api/v1/orders/${params.id}/pack-complete`, { method: "POST" }));
      setGood("Packed quantities match. Ready to ship.");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pack check failed");
    }
  }

  async function dispatch() {
    if (!order?.shipment_id && !shipment) return;
    const id = shipment?.id || order?.shipment_id;
    setError("");
    try {
      setShipment(await api<Shipment>(`/api/v1/shipments/${id}/dispatch`, { method: "POST", body: JSON.stringify({}) }));
      setGood("Dispatched. Outbound stock has been posted.");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dispatch failed");
    }
  }

  if (!order) return <p className="text-sm text-ink/60">{error || "Loading pack station…"}</p>;
  const fileId = order.airway_bill_file_id;
  return (
    <div className="mx-auto max-w-xl">
      <PageHeader title={order.order_number} lede={`${order.customer_name} · ${order.receiver_name}`} />
      {fileId ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={fileUrl(fileId)} alt="Airway bill" className="mb-4 max-h-64 w-full rounded-2xl border border-line object-contain bg-white" />
      ) : (
        <p className="mb-4 text-sm text-ink/60">No airway bill uploaded yet.</p>
      )}
      <ul className="mb-4 space-y-2">
        {order.items.map((item) => {
          const match = item.packed_qty === item.picked_qty && item.picked_qty === item.quantity;
          return (
            <li key={item.id} className={`rounded-2xl border p-3 ${match ? "border-pine/40 bg-pine/5" : "border-line bg-card"}`}>
              <div className="flex justify-between font-medium"><span>{item.sku}</span><span className="font-mono">{item.packed_qty}/{item.picked_qty}</span></div>
              <p className="text-sm text-ink/60">Picked and packed must match</p>
            </li>
          );
        })}
      </ul>
      {["PICKED", "PACKING"].includes(order.status) && <Scanner onScan={onScan} />}
      {error && <div className="mt-3"><Banner>{error}</Banner></div>}
      {good && <div className="mt-3"><Banner tone="good">{good}</Banner></div>}
      {["PICKED", "PACKING"].includes(order.status) && <Button className="mt-4 h-14 w-full" onClick={finish}>Confirm pack</Button>}
      {order.status === "READY_TO_SHIP" && <Button className="mt-4 h-14 w-full" onClick={dispatch}>Dispatch and reduce stock</Button>}
    </div>
  );
}
