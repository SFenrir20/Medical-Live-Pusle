import { useAuth } from "@/context/AuthContext";

export function PrimaryNav({
  active = "Pulso",
  marketing,
}: {
  active?: string;
  marketing?: boolean;
}) {
  const { user } = useAuth();
  const tools =
    (marketing ?? user?.screens.includes("marketing")) &&
    user?.permissions.includes("automation:read");
  const links = [
    ["/", "Pulso"],
    ...(user?.permissions.includes("wa:read") ? [["/embudos", "Embudos"]] : []),
    ["/contactos", "Contactos"],
    ...(tools ? [["/tools", "TOOLS"]] : []),
    ["/ajustes", "Ajustes"],
  ];
  return (
    <nav
      aria-label="Navegación principal"
      className="flex max-w-full items-center gap-1 overflow-x-auto"
    >
      {links.map(([href, label]) => (
        <a
          key={href}
          href={href}
          aria-current={active === label ? "page" : undefined}
          className={`whitespace-nowrap rounded-xl px-3 py-2.5 text-xs font-medium transition sm:px-4 ${active === label ? "bg-primary-soft text-primary" : "text-muted hover:bg-slate-50"}`}
        >
          {label}
        </a>
      ))}
    </nav>
  );
}
