import logo from "@/assets/logo.png";
import logoMark from "@/assets/logo-mark.png";

/** Medical Social Pulse CRM. `mark` is the emblem alone (small spaces, loading screens). */
export function BrandLogo({
  mark = false,
  className = "",
}: {
  mark?: boolean;
  className?: string;
}) {
  return (
    <img
      src={mark ? logoMark : logo}
      alt="Medical Social Pulse CRM"
      draggable={false}
      className={`w-auto select-none ${className}`}
    />
  );
}
