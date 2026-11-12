"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { currentUser } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(currentUser() ? "/dashboard" : "/login");
  }, [router]);
  return <div className="p-8 text-sm text-ink/60">Opening the floor…</div>;
}
