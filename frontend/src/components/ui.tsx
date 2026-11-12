import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function PageHeader({ title, lede, action }: { title: string; lede?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {lede && <p className="mt-1 max-w-2xl text-sm text-ink/70">{lede}</p>}
      </div>
      {action}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-line bg-card p-4 shadow-card ${className}`}>{children}</section>;
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const styles = {
    primary: "bg-ink text-paper hover:bg-ink/90",
    ghost: "border border-line bg-white hover:bg-paper",
    danger: "bg-brick text-white hover:bg-brick/90",
  }[variant];
  return (
    <button
      className={`inline-flex h-11 items-center justify-center rounded-xl px-4 text-sm font-medium disabled:opacity-50 ${styles} ${className}`}
      {...props}
    />
  );
}

export function Field({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`h-11 w-full rounded-xl border border-line bg-white px-3 outline-none ring-amber/30 focus:ring-4 ${className}`}
      {...props}
    />
  );
}

export function Select({ className = "", ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`h-11 w-full rounded-xl border border-line bg-white px-3 outline-none ring-amber/30 focus:ring-4 ${className}`} {...props} />
  );
}

export function Banner({ tone = "bad", children }: { tone?: "bad" | "good"; children: ReactNode }) {
  const styles = tone === "good" ? "border-pine/30 bg-pine/10 text-pine" : "border-brick/30 bg-brick/10 text-brick";
  return <div className={`rounded-xl border px-4 py-3 text-sm font-medium ${styles}`}>{children}</div>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "amber" | "pine" | "brick" }) {
  const styles = {
    neutral: "bg-paper text-ink",
    amber: "bg-amber/15 text-amber",
    pine: "bg-pine/10 text-pine",
    brick: "bg-brick/10 text-brick",
  }[tone];
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${styles}`}>{children}</span>;
}

export function statusTone(status: string): "neutral" | "amber" | "pine" | "brick" {
  if (["SHIPPED", "PICKED", "READY_TO_SHIP"].includes(status)) return "pine";
  if (["CANCELLED"].includes(status)) return "brick";
  if (["PENDING", "PICKING", "PACKING"].includes(status)) return "amber";
  return "neutral";
}
