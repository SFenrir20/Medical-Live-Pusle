import logo from "@/assets/logo.png";
import logoMark from "@/assets/logo-mark.png";
import logoWhite from "@/assets/logo-white.png";

/** Medical Social Pulse CRM. `mark` is the emblem alone (small spaces, loading screens);
 *  `light` is the white version for dark backgrounds. */
export function BrandLogo({
  mark = false,
  light = false,
  className = "",
}: {
  mark?: boolean;
  light?: boolean;
  className?: string;
}) {
  return (
    <img
      src={mark ? logoMark : light ? logoWhite : logo}
      alt="Medical Social Pulse CRM"
      draggable={false}
      className={`w-auto select-none ${className}`}
    />
  );
}
