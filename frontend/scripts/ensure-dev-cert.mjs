import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const certificates = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "certificates");
const cert = path.join(certificates, "dev-cert.pem");
const key = path.join(certificates, "dev-key.pem");

function privateIps() {
  const found = [];
  for (const entries of Object.values(os.networkInterfaces())) {
    for (const entry of entries || []) {
      const family = String(entry.family);
      if ((family !== "IPv4" && family !== "4") || entry.internal) continue;
      const [a, b] = entry.address.split(".").map(Number);
      const privateIp = a === 10 || (a === 192 && b === 168) || (a === 172 && b >= 16 && b <= 31);
      if (privateIp) found.push(entry.address);
    }
  }
  return [...new Set(found)];
}

const wanted = ["127.0.0.1", ...privateIps()];
let text = "";
if (existsSync(cert)) {
  try {
    text = execFileSync("openssl", ["x509", "-in", cert, "-noout", "-ext", "subjectAltName"], { encoding: "utf8" });
  } catch {
    text = "";
  }
}
const have = new Set([...text.matchAll(/IP Address:([0-9.]+)/g)].map((match) => match[1]));
if (text.includes("DNS:localhost") && wanted.every((ip) => have.has(ip))) {
  process.exit(0);
}

mkdirSync(certificates, { recursive: true });
const san = ["DNS:localhost", ...wanted.map((ip) => `IP:${ip}`)].join(",");
execFileSync(
  "openssl",
  [
    "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "825", "-nodes",
    "-keyout", key, "-out", cert,
    "-subj", "/CN=StarLinks Logistics",
    "-addext", `subjectAltName=${san}`,
  ],
  { stdio: "inherit" },
);
console.log(`Dev certificate now includes ${wanted.join(", ")}`);
