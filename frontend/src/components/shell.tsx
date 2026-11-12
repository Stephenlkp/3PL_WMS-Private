"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { BrandMark } from "@/components/brand";
import { clearSession, currentUser, isStaff } from "@/lib/api";
import type { User } from "@/lib/types";

const AuthContext = createContext<User | null>(null);
export function useUser() {
  return useContext(AuthContext);
}

const staffLinks = [
  ["Floor", [
    ["/dashboard", "Dashboard"],
    ["/rack-map", "Rack map"],
    ["/receive", "Receive"],
    ["/picking", "Pick"],
    ["/packing", "Pack"],
  ]],
  ["Stock", [
    ["/inventory", "Inventory"],
    ["/movements", "Movements"],
    ["/search", "Search"],
  ]],
  ["Desk", [
    ["/orders", "Orders"],
    ["/shipments", "Shipments"],
    ["/products", "Products"],
    ["/locations", "Locations"],
    ["/customers", "Customers"],
    ["/reports", "Reports"],
  ]],
] as const;

const customerLinks = [
  ["Account", [
    ["/dashboard", "Dashboard"],
    ["/inventory", "Inventory"],
    ["/orders", "Orders"],
    ["/orders/new", "New order"],
    ["/shipments", "Shipments"],
    ["/movements", "Movements"],
    ["/search", "Search"],
  ]],
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    const existing = currentUser();
    if (!existing) {
      router.replace("/login");
      return;
    }
    setUser(existing);
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
  }, [router]);

  if (!user) return <div className="p-8 text-sm text-ink/60">Opening the floor…</div>;

  const groups = isStaff(user.role) ? staffLinks : customerLinks;
  const mobile = isStaff(user.role)
    ? [["/dashboard", "Home"], ["/picking", "Pick"], ["/receive", "Scan"], ["/packing", "Pack"], ["/search", "Find"]]
    : [["/dashboard", "Home"], ["/inventory", "Stock"], ["/orders", "Orders"], ["/shipments", "Ships"], ["/search", "Find"]];

  return (
    <AuthContext.Provider value={user}>
      <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
        <aside className="hidden bg-ink text-paper md:flex md:flex-col">
          <div className="border-b border-white/10 px-4 py-4">
            <BrandMark tone="dark" />
          </div>
          <nav className="flex-1 space-y-6 overflow-auto px-3 py-5">
            {groups.map(([label, links]) => (
              <div key={label}>
                <p className="px-2 text-[11px] uppercase tracking-[0.16em] text-white/40">{label}</p>
                <div className="mt-2 space-y-1">
                  {links.map(([href, name]) => (
                    <Link
                      key={href}
                      href={href}
                      className={`block rounded-lg px-3 py-2 text-sm ${pathname === href ? "bg-white/10 text-white" : "text-white/75 hover:bg-white/5"}`}
                    >
                      {name}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </nav>
          <div className="border-t border-white/10 px-4 py-4 text-sm">
            <p className="font-medium">{user.full_name}</p>
            <p className="text-white/50">{user.role.replaceAll("_", " ")}</p>
            <button
              className="mt-3 text-amber"
              onClick={() => {
                clearSession();
                router.replace("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </aside>
        <div className="min-w-0">
          <header className="flex items-center justify-between border-b border-line bg-card/80 px-4 py-3 md:hidden">
            <BrandMark size="sm" />
            <button
              className="text-sm text-tide"
              onClick={() => {
                clearSession();
                router.replace("/login");
              }}
            >
              Sign out
            </button>
          </header>
          <main className="px-4 py-5 pb-24 md:px-8 md:pb-8">{children}</main>
        </div>
        <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-line bg-card md:hidden">
          {mobile.map(([href, name]) => (
            <Link key={href} href={href} className={`py-3 text-center text-xs font-medium ${pathname === href ? "text-amber" : "text-ink/70"}`}>
              {name}
            </Link>
          ))}
        </nav>
      </div>
    </AuthContext.Provider>
  );
}
