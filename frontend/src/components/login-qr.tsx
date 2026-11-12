"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui";

export function LoginQr() {
  const [url, setUrl] = useState("");
  const [image, setImage] = useState("");

  useEffect(() => {
    let gone = false;
    fetch("/lan", { cache: "no-store" })
      .then((response) => response.json())
      .then(async (body: { url?: string }) => {
        if (gone || !body.url) return;
        const QRCode = await import("qrcode");
        const dataUrl = await QRCode.toDataURL(body.url, { margin: 1, width: 180, errorCorrectionLevel: "M" });
        if (gone) return;
        setUrl(body.url);
        setImage(dataUrl);
      })
      .catch(() => undefined);
    return () => {
      gone = true;
    };
  }, []);

  return (
    <Card className="flex w-[28rem] max-w-full shrink-0 items-center gap-4 py-3">
      {image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={image} alt="QR code for phone sign-in" className="h-28 w-28 shrink-0" />
      ) : (
        <div className="h-28 w-28 shrink-0 rounded-lg bg-paper" />
      )}
      <div>
        <h2 className="font-semibold">Phone sign-in</h2>
        <p className="mt-1 text-sm text-ink/70">Scan to open sign-in. This address follows the Mac when DHCP changes it.</p>
        <p className="mt-2 break-all font-mono text-xs">{url || "Finding this Mac’s address…"}</p>
      </div>
    </Card>
  );
}
