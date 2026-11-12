export function BrandMark({
  tone = "light",
  size = "md",
}: {
  tone?: "light" | "dark";
  size?: "sm" | "md" | "lg";
}) {
  const logo = { sm: "h-10 w-10", md: "h-24 w-24", lg: "h-36 w-36" }[size];
  const name = tone === "dark" ? "text-paper" : "text-ink";
  return (
    <div className="flex items-center gap-3">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/starlinks-logo.svg" alt="" className={`${logo} shrink-0 object-contain`} />
      <div className={name}>
        <p className="text-sm font-semibold leading-tight">StarLinks</p>
        <p className="text-xs tracking-wide text-current/70">Logistics</p>
      </div>
    </div>
  );
}
