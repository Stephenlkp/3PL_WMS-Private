"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, isManager } from "@/lib/api";
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
      <PageHeader title="Locations" lede="Codes read zone, rack, level. A-02-03 is shown to pickers as A02-03." />
      {isManager(user?.role) && (
        <form onSubmit={create} className="mb-4 flex gap-2">
          <Field placeholder="A-04-01" value={code} onChange={(event) => setCode(event.target.value)} />
          <Button type="submit">Add bin</Button>
        </form>
      )}
      {error && <p className="mb-3 text-sm text-brick">{error}</p>}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {rows.map((location) => (
          <div key={location.id} className="rounded-xl border border-line bg-card px-3 py-3">
            <p className="font-mono">{location.compact_location}</p>
            <p className="text-xs text-ink/50">{location.location_code} · {location.active ? "active" : "inactive"}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
