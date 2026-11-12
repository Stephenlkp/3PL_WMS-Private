"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, isManager } from "@/lib/api";
import { useUser } from "@/components/shell";
import { Button, Field, PageHeader } from "@/components/ui";
import type { Customer } from "@/lib/types";

export default function CustomersPage() {
  const user = useUser();
  const [rows, setRows] = useState<Customer[]>([]);
  const [form, setForm] = useState({ code: "", name: "", email: "" });
  const [error, setError] = useState("");
  function load() { api<Customer[]>("/api/v1/customers").then(setRows).catch((err) => setError(err.message)); }
  useEffect(() => { if (user) load(); }, [user]);

  async function create(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/api/v1/customers", { method: "POST", body: JSON.stringify(form) });
      setForm({ code: "", name: "", email: "" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the customer");
    }
  }

  return (
    <div>
      <PageHeader title="Customers" lede="Each customer is a tenant. Their users only see their own stock, orders, and files." />
      {isManager(user?.role) && (
        <form onSubmit={create} className="mb-4 grid gap-2 md:grid-cols-4">
          <Field placeholder="Code" value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} required />
          <Field placeholder="Name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
          <Field placeholder="Email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
          <Button type="submit">Add customer</Button>
        </form>
      )}
      {error && <p className="mb-3 text-sm text-brick">{error}</p>}
      <ul className="space-y-2">
        {rows.map((customer) => (
          <li key={customer.id} className="rounded-xl border border-line bg-card px-4 py-3">
            <span className="font-mono text-sm">{customer.code}</span>
            <span className="ml-3 font-medium">{customer.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
