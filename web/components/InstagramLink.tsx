import Link from "next/link";

export const INSTAGRAM_URL = "https://www.instagram.com/entreinterioresrobe/";
export const INSTAGRAM_HANDLE = "@entreinterioresrobe";

/** Enlace a la cuenta de Instagram de Entre Interiores, con el logo de IG.
 *  `rel="me"` refuerza la identidad (par del sameAs del JSON-LD). */
export default function InstagramLink({
  className = "",
  size = 20,
  showHandle = false,
}: {
  className?: string;
  size?: number;
  showHandle?: boolean;
}) {
  return (
    <Link
      href={INSTAGRAM_URL}
      target="_blank"
      rel="me noopener noreferrer"
      data-cursor="hover"
      aria-label="Entre Interiores en Instagram"
      className={`inline-flex items-center gap-2 ${className}`}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        aria-hidden="true"
      >
        <rect x="2.5" y="2.5" width="19" height="19" rx="5.2" />
        <circle cx="12" cy="12" r="4.1" />
        <circle cx="17.6" cy="6.4" r="1.15" fill="currentColor" stroke="none" />
      </svg>
      {showHandle && (
        <span className="font-mono text-[11px] tracking-[1px]">
          {INSTAGRAM_HANDLE}
        </span>
      )}
    </Link>
  );
}
