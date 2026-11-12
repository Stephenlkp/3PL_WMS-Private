"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, barcodeUrl, isManager, isStaff } from "@/lib/api";
import { useUser } from "@/components/shell";
import { Button, Field, PageHeader, Select } from "@/components/ui";
import type { Balance, Customer, Product } from "@/lib/types";

export default function ProductsPage() {
  const user = useUser();
  const [products, setProducts] = useState<Product[]>([]);
  const [balances, setBalances] = useState<Balance[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [barcodes, setBarcodes] = useState<Record<string, string>>({});
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [form, setForm] = useState({ customer_id: "", sku: "", name: "", barcode: "" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function load() {
    api<Product[]>("/api/v1/products").then((rows) => {
      setProducts(rows);
      setBarcodes(Object.fromEntries(rows.map((product) => [product.id, product.barcode])));
    }).catch((err) => setError(err.message));
    api<Balance[]>("/api/v1/inventory/balances?view=location").then((rows) => {
      setBalances(rows);
      setQuantities(Object.fromEntries(rows.filter((row) => row.location_id).map((row) => [`${row.product_id}:${row.location_id}`, String(row.location_qty ?? 0)])));
    }).catch(() => undefined);
  }
  useEffect(() => {
    if (!user) return;
    load();
    if (isStaff(user.role)) api<Customer[]>("/api/v1/customers").then(setCustomers).catch(() => undefined);
  }, [user]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api("/api/v1/products", {
        method: "POST",
        body: JSON.stringify({
          customer_id: isStaff(user?.role) ? form.customer_id || customers[0]?.id : undefined,
          sku: form.sku,
          name: form.name || form.sku,
          barcode: form.barcode || form.sku,
        }),
      });
      setForm({ ...form, sku: "", name: "", barcode: "" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the product");
    }
  }

  async function saveBarcode(product: Product) {
    setError("");
    setNotice("");
    try {
      await api(`/api/v1/products/${product.id}`, {
        method: "PATCH",
        body: JSON.stringify({ barcode: barcodes[product.id] || product.sku }),
      });
      setNotice(`${product.sku} barcode saved. It still points at this SKU.`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the barcode");
    }
  }

  async function saveQuantity(row: Balance) {
    if (!row.location_id) return;
    const key = `${row.product_id}:${row.location_id}`;
    const next = Number(quantities[key]);
    const current = row.location_qty ?? 0;
    if (!Number.isFinite(next) || next < 0 || next === current) return;
    setError("");
    setNotice("");
    try {
      await api("/api/v1/inventory/adjust", {
        method: "POST",
        body: JSON.stringify({
          product_id: row.product_id,
          location_id: row.location_id,
          quantity: next - current,
          notes: `Set ${row.sku} at ${row.location_code} from ${current} to ${next}`,
        }),
      });
      setNotice(`${row.sku} at ${row.compact_location || row.location_code} is now ${next}.`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the quantity");
    }
  }

  const canEdit = isManager(user?.role) || user?.role === "customer";
  const canCorrectQty = isManager(user?.role);

  return (
    <div>
      <PageHeader title="Products" lede="A new product starts with the barcode equal to the SKU. Change the barcode when the printed label is different. The barcode still points at that SKU. Quantity changes are posted to the ledger." />
      {canEdit && <form onSubmit={create} className="mb-6 grid gap-2 md:grid-cols-4">
        {isStaff(user?.role) && (
          <Select value={form.customer_id} onChange={(event) => setForm({ ...form, customer_id: event.target.value })}>
            <option value="">Customer</option>
            {customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}</option>)}
          </Select>
        )}
        <Field placeholder="SKU" value={form.sku} onChange={(event) => setForm({ ...form, sku: event.target.value })} required />
        <Field placeholder="Barcode, blank uses the SKU" value={form.barcode} onChange={(event) => setForm({ ...form, barcode: event.target.value })} />
        <Field placeholder="Name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        <Button type="submit">Add product</Button>
      </form>}
      {error && <p className="mb-3 text-sm text-brick">{error}</p>}
      {notice && <p className="mb-3 text-sm text-pine">{notice}</p>}
      <div className="grid gap-3">
        {products.map((product) => {
          const stock = balances.filter((row) => row.product_id === product.id && row.location_id);
          return (
            <article key={product.id} className="rounded-2xl border border-line bg-card p-3">
              <div className="flex gap-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={barcodeUrl(product.id)} alt={`${product.sku} barcode`} className="h-16 w-36 object-contain" />
                <div className="min-w-0">
                  <p className="font-semibold">{product.sku}</p>
                  <p className="text-sm">{product.name}</p>
                  <p className="text-xs text-ink/60">{product.customer_name}</p>
                </div>
              </div>
              {canEdit && (
                <div className="mt-3 flex gap-2">
                  <Field value={barcodes[product.id] ?? product.barcode} onChange={(event) => setBarcodes({ ...barcodes, [product.id]: event.target.value })} aria-label={`${product.sku} barcode`} />
                  <Button type="button" className="shrink-0" onClick={() => saveBarcode(product)}>Save barcode</Button>
                </div>
              )}
              <ul className="mt-3 space-y-2 text-sm">
                {stock.length === 0 && <li className="text-ink/50">No stock on hand.</li>}
                {stock.map((row) => {
                  const key = `${row.product_id}:${row.location_id}`;
                  return (
                    <li key={key} className="flex items-center gap-2">
                      <span className="w-20 font-mono">{row.compact_location || row.location_code}</span>
                      {canCorrectQty ? (
                        <>
                          <Field className="w-24" inputMode="numeric" value={quantities[key] ?? String(row.location_qty ?? 0)} onChange={(event) => setQuantities({ ...quantities, [key]: event.target.value })} aria-label={`${product.sku} quantity at ${row.location_code}`} />
                          <Button type="button" variant="ghost" onClick={() => saveQuantity(row)}>Set quantity</Button>
                        </>
                      ) : (
                        <span className="font-mono">{row.location_qty ?? 0}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </article>
          );
        })}
      </div>
    </div>
  );
}
