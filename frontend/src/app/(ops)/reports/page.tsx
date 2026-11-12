"use client";

import { useEffect, useState } from "react";
import { api, downloadReport, isManager } from "@/lib/api";
import { useUser } from "@/components/shell";
import { Button, PageHeader, Select } from "@/components/ui";
import type { Customer } from "@/lib/types";

const reports = [
  ["Inventory", "inventory", "inventory-report"],
  ["Stock aging", "aging", "stock-aging"],
  ["Movements", "movements", "inventory-movements"],
  ["Order fulfillment", "fulfillment", "order-fulfillment"],
  ["Shipments", "shipments", "shipments"],
  ["Customer billing", "billing", "customer-billing"],
];

export default function ReportsPage() {
  const user = useUser();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState("");
  useEffect(() => {
    if (user && isManager(user.role)) {
      api<Customer[]>("/api/v1/customers").then((rows) => {
        setCustomers(rows);
        setCustomerId(rows[0]?.id || "");
      }).catch(() => undefined);
    }
  }, [user]);
  const visible = reports.filter(([label]) => label !== "Customer billing" || isManager(user?.role) || user?.role === "customer");
  return (
    <div>
      <PageHeader title="Reports" lede="Exports are generated from the ledger. Billing uses the customer rate card: storage is a snapshot, inbound and pick-pack use the period's activity." />
      {isManager(user?.role) && (
        <Select className="mb-4 max-w-sm" value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
          {customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}</option>)}
        </Select>
      )}
      <div className="space-y-3">
        {visible.map(([label, slug, filename]) => (
          <div key={slug} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-line bg-card px-4 py-3">
            <p className="font-medium">{label}</p>
            <div className="flex gap-2">
              {["csv", "xlsx", "pdf"].map((format) => (
                <Button
                  key={format}
                  variant="ghost"
                  onClick={() => {
                    const params = new URLSearchParams({ format });
                    if (slug === "billing" && customerId) params.set("customer_id", customerId);
                    downloadReport(`/api/v1/reports/${slug}?${params}`, `${filename}.${format}`);
                  }}
                >
                  {format.toUpperCase()}
                </Button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
