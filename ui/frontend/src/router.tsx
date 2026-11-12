import { useEffect, useState, type AnchorHTMLAttributes, type MouseEvent } from "react";

// Routeur minimal (History API) sous /ui.
const BASE = "/ui";
const listeners = new Set<() => void>();

export function navigate(to: string, replace = false) {
  const url = BASE + (to.startsWith("/") ? to : `/${to}`);
  if (replace) history.replaceState(null, "", url);
  else history.pushState(null, "", url);
  listeners.forEach((l) => l());
}

function current() {
  const path = location.pathname.startsWith(BASE) ? location.pathname.slice(BASE.length) || "/" : "/";
  return { path, search: new URLSearchParams(location.search) };
}

export function useLocation() {
  const [loc, setLoc] = useState(current);
  useEffect(() => {
    const update = () => setLoc(current());
    listeners.add(update);
    window.addEventListener("popstate", update);
    return () => {
      listeners.delete(update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  return loc;
}

export function Link({ to, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  return (
    <a
      href={BASE + to}
      onClick={(e: MouseEvent<HTMLAnchorElement>) => {
        onClick?.(e);
        if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigate(to);
        window.scrollTo({ top: 0 });
      }}
      {...rest}
    />
  );
}
