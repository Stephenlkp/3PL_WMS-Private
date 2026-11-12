"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, isManager, locationBarcodeUrl } from "@/lib/api";
import { useUser } from "@/components/shell";
import { Button, Field, PageHeader } from "@/components/ui";
import type { Location } from "@/lib/types";

export default function LocationsPage() {
  const user = useUser();
  const [rows, setRows] = useState<Location[]>([]);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  function load() { api<Location[]>("/api/v1/locations").then(setRows).catch((err) => setError(err.message)); }
  useEffect(() => { if (user) load(); }, [user]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api("/api/v1/locations", { method: "POST", body: JSON.stringify({ location_code: code }) });
      setCode("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the location");
    }
  }

  return (
    <div>
      <PageHeader title="Locations" lede="Each bin has a QR of its location code. Print these and stick them on the racks. Receive reads that QR before any product." />
      <div className="mb-4 flex flex-wrap items-center gap-2 print:hidden">
      {isManager(user?.role) && (
        <form onSubmit={create} className="flex min-w-[16rem] flex-1 gap-2">
          <Field placeholder="A-04-01" value={code} onChange={(event) => setCode(event.target.value)} />
          <Button type="submit" className="shrink-0">Add bin</Button>
        </form>
      )}
        <Button type="button" variant="ghost" className="shrink-0" onClick={() => window.print()}>Print bin QR labels</Button>
      </div>
      {error && <p className="mb-3 text-sm text-brick">{error}</p>}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 print:grid-cols-3">
        {rows.map((location) => (
          <div key={location.id} className="rounded-xl border border-line bg-card px-3 py-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={locationBarcodeUrl(location.id)} alt={`${location.location_code} QR`} className="mx-auto h-28 w-28 object-contain" />
            <p className="mt-2 text-center font-mono">{location.compact_location}</p>
            <p className="text-center text-xs text-ink/50">{location.location_code} · {location.active ? "active" : "inactive"}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
