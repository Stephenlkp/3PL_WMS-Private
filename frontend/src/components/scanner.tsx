"use client";

import { useEffect, useRef, useState } from "react";
import { playScan, primeScanSound } from "@/lib/sound";

type Html5Module = typeof import("html5-qrcode");

export function Scanner({
  onScan,
  placeholder = "Scan barcode",
}: {
  onScan: (code: string) => void | boolean | Promise<void | boolean>;
  placeholder?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const onScanRef = useRef(onScan);
  const last = useRef({ code: "", at: 0 });
  const scannerRef = useRef<{ stop: () => Promise<void> } | null>(null);
  const libraryRef = useRef<Html5Module | null>(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [cameraError, setCameraError] = useState("");
  onScanRef.current = onScan;

  async function emit(raw: string) {
    const code = raw.trim();
    if (!code) return;
    const now = Date.now();
    if (code === last.current.code && now - last.current.at < 1200) return;
    last.current = { code, at: now };
    primeScanSound();
    let accepted = true;
    try {
      const result = await onScanRef.current(code);
      accepted = result !== false;
    } catch {
      accepted = false;
    }
    playScan(accepted);
    if (inputRef.current) {
      inputRef.current.value = "";
      inputRef.current.focus();
    }
  }

  useEffect(() => {
    inputRef.current?.focus();
    import("html5-qrcode").then((library) => {
      libraryRef.current = library;
    }).catch(() => undefined);
    return () => {
      scannerRef.current?.stop().catch(() => undefined);
    };
  }, []);

  async function stopCamera() {
    await scannerRef.current?.stop().catch(() => undefined);
    scannerRef.current = null;
    setCameraOn(false);
  }

  async function toggleCamera() {
    if (cameraOn) {
      await stopCamera();
      return;
    }
    setCameraError("");
    primeScanSound();
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      const host = window.location.hostname;
      setCameraError(`The camera needs a secure page. On this iPhone open https://${host}:3000, accept the certificate, then tap Scan with camera.`);
      return;
    }
    let probe: MediaStream;
    try {
      probe = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" } },
      });
    } catch (error) {
      setCameraError(cameraMessage(error));
      return;
    }
    probe.getTracks().forEach((track) => track.stop());
    setCameraOn(true);
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    try {
      const library = libraryRef.current || (await import("html5-qrcode"));
      libraryRef.current = library;
      const scanner = new library.Html5Qrcode("wms-camera", {
        formatsToSupport: [library.Html5QrcodeSupportedFormats.CODE_128, library.Html5QrcodeSupportedFormats.QR_CODE],
        verbose: false,
      });
      await scanner.start(
        { facingMode: "environment" },
        {
          fps: 8,
          qrbox: (width, height) => ({
            width: Math.max(180, Math.floor(width * 0.88)),
            height: Math.max(90, Math.floor(Math.min(160, height * 0.45))),
          }),
        },
        (text) => emit(text),
        () => undefined,
      );
      scannerRef.current = scanner;
    } catch (error) {
      setCameraOn(false);
      setCameraError(cameraMessage(error));
    }
  }

  return (
    <div className="space-y-3">
      <input
        ref={inputRef}
        className="h-16 w-full rounded-2xl border-2 border-ink bg-white px-4 font-mono text-xl outline-none ring-amber/40 focus:ring-4"
        placeholder={placeholder}
        autoCapitalize="characters"
        autoCorrect="off"
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            emit((event.target as HTMLInputElement).value);
          }
        }}
      />
      <button type="button" onClick={toggleCamera} className="h-14 w-full rounded-2xl bg-tide text-lg font-medium text-white">
        {cameraOn ? "Stop camera" : "Scan with camera"}
      </button>
      {cameraError && <p className="text-sm text-brick">{cameraError}</p>}
      <div id="wms-camera" className={cameraOn ? "min-h-52 overflow-hidden rounded-2xl bg-black" : "hidden"} />
      <p className="text-sm text-ink/60">A USB scanner types into this box and sends Enter. The camera reads Code 128 bin and product labels.</p>
    </div>
  );
}

function cameraMessage(error: unknown) {
  const text = error instanceof Error ? error.message : String(error || "");
  if (/secure context|https or localhost/i.test(text)) {
    return "The camera needs https. Open the secure address, accept the certificate, then try again.";
  }
  if (/NotAllowed|permission/i.test(text)) {
    return "Camera permission was denied. Allow the camera for this site in iPhone Settings, then try again.";
  }
  if (/not found|NotFound|no camera/i.test(text)) {
    return "No camera was found on this device.";
  }
  return text || "Camera unavailable";
}
