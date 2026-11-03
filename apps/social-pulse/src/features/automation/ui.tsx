import { ReactNode } from "react";

export function Section({
  title,
  help,
  action,
  children,
}: {
  title: string;
  help?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mt-6">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <h2 className="text-xl font-bold">{title}</h2>
          {help && <p className="mt-1 max-w-3xl text-sm text-muted">{help}</p>}
        </div>
        {action}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

export function Banner({
  tone,
  children,
}: {
  tone: "info" | "warn" | "error" | "ok";
  children: ReactNode;
}) {
  const styles = {
    info: "border-sky-200 bg-sky-50 text-sky-800",
    warn: "border-amber-200 bg-amber-50 text-amber-900",
    error: "border-red-200 bg-red-50 text-red-700",
    ok: "border-emerald-200 bg-emerald-50 text-emerald-800",
  }[tone];
  return (
    <p
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-xl border px-4 py-3 text-sm ${styles}`}
    >
      {children}
    </p>
  );
}

export function Toggle({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${
        checked ? "bg-primary" : "bg-slate-300"
      }`}
    >
      <span
        className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition ${
          checked ? "left-[22px]" : "left-0.5"
        }`}
      />
    </button>
  );
}

export const inputClass =
  "w-full rounded-xl border border-line bg-white px-3 py-2 text-sm outline-none focus:border-primary";
export const buttonClass =
  "rounded-xl bg-primary px-4 py-2 text-sm font-bold text-white hover:bg-primary-dark disabled:opacity-50";
export const ghostButtonClass =
  "rounded-xl border border-line bg-white px-4 py-2 text-sm font-semibold text-ink hover:bg-slate-50 disabled:opacity-50";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-xs font-bold text-ink">{label}</span>
      {hint && <span className="ml-2 text-[11px] text-muted">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  );
}

export const when = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("es-PE", {
        timeZone: "America/Lima",
        day: "2-digit",
        month: "2-digit",
        hour: "numeric",
        minute: "2-digit",
      })
    : "—";
