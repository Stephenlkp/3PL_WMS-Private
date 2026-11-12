"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Scanner } from "@/components/scanner";
import { Banner, Button, Card, Field, PageHeader } from "@/components/ui";
import type { Location, Product } from "@/lib/types";

type Line = { sku: string; barcode: string; quantity: number };

function locationCode(raw: string) {
  const code = raw.trim().toUpperCase();
  if (/^[A-Z]{1,3}-\d{2}-\d{2}$/.test(code)) return code;
  const compact = code.match(/^([A-Z]{1,3})(\d{2})-(\d{2})$/);
  if (compact) return `${compact[1]}-${compact[2]}-${compact[3]}`;
  return null;
}

export default function ReceivePage() {
  const [location, setLocation] = useState<Location | null>(null);
  const [qty, setQty] = useState("1");
  const [lines, setLines] = useState<Line[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function onScan(code: string) {
    setError("");
    setMessage("");
    if (!location) {
      const normalized = locationCode(code);
      if (!normalized) {
        setError("Scan a bin first. Product labels are ignored until a location is on screen.");
        return false;
      }
      const rows = await api<Location[]>(`/api/v1/locations?q=${encodeURIComponent(normalized)}`);
      const match = rows.find((row) => row.location_code === normalized && row.active);
      if (!match) {
        setError(`${normalized} is not a bin in this warehouse.`);
        return false;
      }
      setLocation(match);
      return true;
    }
    try {
      const product = await api<Product>(`/api/v1/products/lookup?code=${encodeURIComponent(code)}`);
      setLines((current) => [...current, { sku: product.sku, barcode: product.barcode, quantity: Number(qty) || 1 }]);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "That code is not a catalog SKU.");
      return false;
    }
  }

  async function post() {
    if (!location) return;
    setError("");
    setMessage("");
    try {
      const result = await api<{ reference_no: string }>("/api/v1/inventory/receive", {
        method: "POST",
        body: JSON.stringify({
          location_code: location.location_code,
          lines: lines.map((line) => ({ barcode: line.barcode, quantity: line.quantity })),
        }),
      });
      setMessage(`Receipt ${result.reference_no} posted to ${location.compact_location}.`);
      setLines([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Receive failed");
    }
  }

  return (
    <div className="mx-auto max-w-xl">
      <PageHeader
        title="Receive"
        lede={location ? "Scan catalog products into this bin. Unknown labels are refused." : "Scan a bin label before any product."}
      />
      <Card className="space-y-4">
        <div>
          <p className="text-sm text-ink/60">Location</p>
          <p className="font-mono text-3xl">{location ? location.compact_location : "Scan a bin"}</p>
          {location && (
            <button type="button" className="mt-2 text-sm text-tide" onClick={() => { setLocation(null); setLines([]); setMessage(""); }}>
              Scan a different bin
            </button>
          )}
        </div>
        {location && (
          <label className="block text-sm">
            Quantity for the next scan
            <Field className="mt-1" value={qty} onChange={(event) => setQty(event.target.value)} inputMode="numeric" />
          </label>
        )}
        <Scanner onScan={onScan} placeholder={location ? "Scan a product" : "Scan a bin"} />
        {location && (
          <ul className="space-y-2 text-sm">
            {lines.map((line, index) => (
              <li key={`${line.sku}-${index}`} className="flex justify-between font-mono">
                <span>{line.sku}</span>
                <span>{line.quantity}</span>
              </li>
            ))}
          </ul>
        )}
        {error && <Banner>{error}</Banner>}
        {message && <Banner tone="good">{message}</Banner>}
        <Button className="h-14 w-full text-base" disabled={!location || lines.length === 0} onClick={post}>
          Post receipt
        </Button>
      </Card>
    </div>
  );
}
