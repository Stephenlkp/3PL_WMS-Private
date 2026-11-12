"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, isStaff } from "@/lib/api";
import { useUser } from "@/components/shell";
import { Banner, Button, Field, PageHeader, Select } from "@/components/ui";
import type { Customer, Product } from "@/lib/types";

export default function NewOrderPage() {
  const user = useUser();
  const router = useRouter();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [lines, setLines] = useState<{ product_id: string; sku: string; quantity: number }[]>([]);
  const [receiver, setReceiver] = useState({ receiver_name: "", receiver_phone: "", receiver_address: "", courier: "J&T Express", tracking_number: "" });
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    if (isStaff(user.role)) {
      api<Customer[]>("/api/v1/customers").then((rows) => {
        setCustomers(rows);
        setCustomerId(rows[0]?.id || "");
      });
    }
  }, [user]);

  useEffect(() => {
    if (!user) return;
    const scoped = isStaff(user.role) ? customerId : user.customer_id;
    if (!scoped) return;
    api<Product[]>(`/api/v1/products?customer_id=${scoped}`).then((rows) => {
      setProducts(rows);
      setProductId(rows[0]?.id || "");
    });
  }, [user, customerId]);

  async function submit() {
    setError("");
    try {
      const order = await api<{ id: string }>("/api/v1/orders", {
        method: "POST",
        body: JSON.stringify({
          customer_id: isStaff(user?.role) ? customerId : undefined,
          ...receiver,
          tracking_number: receiver.tracking_number || null,
          idempotency_key: crypto.randomUUID().slice(0, 40),
          items: lines.map((line) => ({ product_id: line.product_id, quantity: line.quantity })),
        }),
      });
      router.push(`/orders/${order.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Order failed");
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="New order" lede="Creating the order posts a RESERVED transaction. Available stock drops. The bin quantity does not." />
      <div className="space-y-3">
        {isStaff(user?.role) && (
          <Select value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
            {customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}</option>)}
          </Select>
        )}
        {(["receiver_name", "receiver_phone", "receiver_address", "courier", "tracking_number"] as const).map((key) => (
          <Field key={key} placeholder={key.replaceAll("_", " ")} value={receiver[key]} onChange={(event) => setReceiver({ ...receiver, [key]: event.target.value })} />
        ))}
        <div className="grid grid-cols-[1fr_90px_auto] gap-2">
          <Select value={productId} onChange={(event) => setProductId(event.target.value)}>
            {products.map((product) => <option key={product.id} value={product.id}>{product.sku} · {product.name}</option>)}
          </Select>
          <Field value={quantity} onChange={(event) => setQuantity(event.target.value)} />
          <Button type="button" onClick={() => {
            const product = products.find((item) => item.id === productId);
            if (!product) return;
            setLines((current) => current.filter((line) => line.product_id !== product.id).concat({ product_id: product.id, sku: product.sku, quantity: Number(quantity) || 1 }));
          }}>Add</Button>
        </div>
        <ul className="text-sm">
          {lines.map((line) => <li key={line.product_id} className="flex justify-between border-b border-line py-2"><span>{line.sku}</span><span className="font-mono">{line.quantity}</span></li>)}
        </ul>
        {error && <Banner>{error}</Banner>}
        <Button className="h-12 w-full" disabled={lines.length === 0} onClick={submit}>Reserve stock and create order</Button>
      </div>
    </div>
  );
}
