import Link from "next/link";

type LinkMode = "anchor" | "route";

const NAV_ITEMS = [
  { href: "#home", label: "Home" },
  { href: "#services", label: "Services" },
  { href: "#why", label: "Talent" },
  { href: "#contact", label: "Contact" },
];

export default function SiteHeader({ linkMode = "anchor" }: { linkMode?: LinkMode }) {
  const isRouteMode = linkMode === "route";
  const toHref = (fragment: string) => (isRouteMode ? `/${fragment}` : fragment);

  return (
    <header className="sticky top-0 z-20 w-full border-b border-orange-200 bg-orange-50/90 backdrop-blur">
      <nav className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        {isRouteMode ? (
          <Link href="/" className="text-xl font-bold tracking-tight sm:text-2xl">
            Nexova
          </Link>
        ) : (
          <span className="text-xl font-bold tracking-tight sm:text-2xl">Nexova</span>
        )}
        <ul className="flex flex-wrap justify-center gap-x-4 gap-y-2 text-sm text-orange-900 sm:justify-end sm:space-x-6 sm:text-base md:text-lg">
          {NAV_ITEMS.map((item) => (
            <li key={item.href}>
              {isRouteMode ? (
                <Link href={toHref(item.href)} className="hover:text-rose-600">
                  {item.label}
                </Link>
              ) : (
                <a href={toHref(item.href)} className="nav-link hover:text-rose-600">
                  {item.label}
                </a>
              )}
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
