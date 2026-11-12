"use client";

import { useEffect, useMemo, useState } from "react";
import { api, fileUrl } from "@/lib/api";
import { Banner, Card, Field, PageHeader } from "@/components/ui";
import type { RackMap, SkuHit } from "@/lib/types";

export default function RackMapPage() {
  const [map, setMap] = useState<RackMap | null>(null);
  const [query, setQuery] = useState("MRO400EU");
  const [hits, setHits] = useState<SkuHit[]>([]);
  const [selected, setSelected] = useState<LocationStock | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<RackMap>("/api/v1/locations/map").then(setMap).catch((err) => setError(err.message));
    api<SkuHit[]>(`/api/v1/locations/find-sku?q=${encodeURIComponent(query)}`).then(setHits).catch(() => undefined);
    // The opening search is the iSpring unit stored on the photographed rack.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const highlight = useMemo(() => new Set(hits.flatMap((hit) => hit.placements.map((place) => place.location_id))), [hits]);
  const max = useMemo(() => {
    const values = map?.zones.flatMap((zone) => zone.racks.flatMap((rack) => rack.cells.map((cell) => cell.physical_qty))) || [1];
    return Math.max(1, ...values);
  }, [map]);

  async function find(event?: { preventDefault: () => void }) {
    event?.preventDefault();
    setError("");
    try {
      setHits(await api<SkuHit[]>(`/api/v1/locations/find-sku?q=${encodeURIComponent(query)}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    }
  }

  async function openCell(id: string) {
    const [stock, cells] = await Promise.all([
      api<LocationStock["rows"]>(`/api/v1/locations/${id}/stock`),
      Promise.resolve(map?.zones.flatMap((zone) => zone.racks.flatMap((rack) => rack.cells)) || []),
    ]);
    const cell = cells.find((item) => item.id === id);
    setSelected(cell ? { cell, rows: stock } : null);
  }

  const hero = hits[0];

  return (
    <div>
      <PageHeader title="Rack map" lede="Same zone, then rack, then level. Search a SKU to light the bin and open its photo." />
      <form onSubmit={find} className="mb-4 flex gap-2">
        <Field value={query} onChange={(event) => setQuery(event.target.value)} placeholder="SKU, barcode, or name" />
        <button className="h-11 rounded-xl bg-ink px-4 text-sm text-paper">Find</button>
      </form>
      {error && <div className="mb-4"><Banner>{error}</Banner></div>}
      {hero && (
        <Card className="mb-4 grid gap-4 md:grid-cols-[180px_1fr]">
          {hero.placements[0]?.photo_file_id ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={fileUrl(hero.placements[0].photo_file_id)} alt={`Rack ${hero.placements[0].compact_location}`} className="h-36 w-full rounded-xl object-cover" />
          ) : (
            <div className="flex h-36 items-center justify-center rounded-xl bg-tide text-sm text-white">No rack photo</div>
          )}
          <div>
            <p className="text-sm text-ink/60">{hero.customer_name} · {hero.name}</p>
            <p className="mt-1 text-3xl font-semibold">{hero.sku}</p>
            <p className="mt-2 font-mono text-lg">Rack {hero.placements[0]?.compact_location || "—"} · Stock {hero.placements[0]?.physical_qty ?? hero.on_hand_qty}</p>
            <p className="text-sm text-ink/60">On hand {hero.on_hand_qty} · Reserved {hero.reserved_qty} · Available {hero.available_qty}</p>
          </div>
        </Card>
      )}
      <div className="space-y-6">
        {map?.zones.map((zone) => (
          <section key={zone.zone}>
            <h2 className="mb-2 text-sm uppercase tracking-[0.16em] text-ink/50">{zone.zone} zone</h2>
            <div className="grid gap-3 md:grid-cols-3">
              {zone.racks.map((rack) => (
                <Card key={rack.rack} className="!p-3">
                  <p className="mb-2 font-mono text-sm">{zone.zone}{rack.rack}</p>
                  <div className="grid gap-2">
                    {rack.cells.map((cell) => {
                      const heat = cell.physical_qty === 0 ? "heat-0" : cell.physical_qty / max > 0.66 ? "heat-3" : cell.physical_qty / max > 0.33 ? "heat-2" : "heat-1";
                      return (
                        <button
                          key={cell.id}
                          onClick={() => openCell(cell.id)}
                          className={`rounded-xl border px-3 py-3 text-left ${heat} ${highlight.has(cell.id) ? "border-amber ring-2 ring-amber" : "border-transparent"}`}
                        >
                          <span className="font-mono text-sm">{cell.compact_location}</span>
                          <span className="mt-1 block text-lg font-semibold">{cell.physical_qty}</span>
                        </button>
                      );
                    })}
                  </div>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>
      {selected && (
        <Card className="mt-4">
          <h2 className="font-mono text-lg">{selected.cell.compact_location}</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {selected.rows.length === 0 && <li className="text-ink/50">Bin is empty for your view.</li>}
            {selected.rows.map((row) => (
              <li key={row.product_id} className="flex justify-between"><span>{row.sku} · {row.product_name}</span><span className="font-mono">{row.physical_qty}</span></li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

type LocationStock = {
  cell: { id: string; compact_location: string };
  rows: { product_id: string; sku: string; product_name: string; physical_qty: number }[];
};
