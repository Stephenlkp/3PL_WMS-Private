import dgram from "dgram";
import os from "os";

function isPrivate(ip: string) {
  const parts = ip.split(".").map((part) => Number(part));
  if (parts.length !== 4 || parts.some((part) => Number.isNaN(part))) return false;
  if (parts[0] === 10) return true;
  if (parts[0] === 192 && parts[1] === 168) return true;
  return parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31;
}

/** Private IPv4 addresses currently assigned to this computer. */
export function privateIpv4(): string[] {
  try {
    const found: string[] = [];
    for (const entries of Object.values(os.networkInterfaces())) {
      for (const entry of entries || []) {
        const family = String(entry.family);
        if ((family !== "IPv4" && family !== "4") || entry.internal) continue;
        if (isPrivate(entry.address)) found.push(entry.address);
      }
    }
    return [...new Set(found)];
  } catch {
    return [];
  }
}

/** Address the operating system would use to reach the LAN. Follows DHCP. */
export function outboundIpv4(): Promise<string | null> {
  return new Promise((resolve) => {
    const socket = dgram.createSocket("udp4");
    const finish = (ip: string | null) => {
      socket.close();
      resolve(ip && isPrivate(ip) ? ip : null);
    };
    socket.once("error", () => finish(null));
    try {
      socket.connect(80, "8.8.8.8", () => {
        const address = socket.address();
        finish(typeof address === "object" ? address.address : null);
      });
    } catch {
      finish(null);
    }
  });
}

export async function phoneLoginUrl(hostHeader: string, protocol: string) {
  const override = process.env.LOGIN_URL?.trim();
  if (override) {
    const parsed = new URL(override);
    return { host: parsed.hostname, url: override.replace(/\/$/, "") };
  }
  const [headerHost, headerPort] = hostHeader.split(":");
  const locals = privateIpv4();
  const onThisMachine = locals.includes(headerHost) ? headerHost : null;
  const host = onThisMachine || (await outboundIpv4()) || locals[0] || "localhost";
  const port = headerPort || "3000";
  const scheme = protocol === "http" ? "http" : "https";
  return { host, url: `${scheme}://${host}:${port}/login` };
}
