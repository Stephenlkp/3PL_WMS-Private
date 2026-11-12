import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Outfit } from "next/font/google";
import "./globals.css";

const sans = Outfit({ subsets: ["latin"], variable: "--font-sans" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "StarLinks Logistics",
  description: "StarLinks Logistics warehouse management for receiving, picking, packing, and shipping.",
  manifest: "/manifest.json",
  icons: { icon: "/starlinks-logo.svg", apple: "/starlinks-logo.svg" },
  appleWebApp: { capable: true, title: "StarLinks Logistics", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: "#1c1915",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${mono.variable} font-sans antialiased`}>{children}</body>
    </html>
  );
}
