import type { CSSProperties } from "react";
const paths = {
  archive: "M3 4h18v5H3zM5 9v11h14V9M9 13h6",
  dashboard: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h5",
  upload: "M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4",
  search: "m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  arrow: "m14 6-6 6 6 6M8 12h13",
  download: "M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4",
  shield: "m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6zM8 12l3 3 5-6",
  clock: "M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "m6 6 12 12M6 18 18 6",
  check: "m5 12 4 4L19 6",
  folder: "M3 7V4h6l2 3h10v13H3z",
  refresh: "M20 7a9 9 0 1 0 1 8M20 2v6h-6",
  image: "M3 3h18v18H3zM3 17l6-6 5 5 3-3 4 4M17 7h.01",
  user: "M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10",
  users: "M16 21a6 6 0 0 0-12 0M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21a5 5 0 0 0-4-4.9M15 3.1a4 4 0 0 1 0 7.8",
  logout: "M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3",
  scan: "M3 7V4h3M21 7V4h-3M3 17v3h3M21 17v3h-3M7 12h10",
  alert: "M12 9v4M12 17h.01M10.3 3.9 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0",
  play: "m7 4 13 8-13 8z",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
} as const;
export type IconName = keyof typeof paths;
export function Icon({ name, className = "", style }: { name: IconName; className?: string; style?: CSSProperties }) {
  return <svg aria-hidden="true" className={`icon ${className}`} style={style} width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg>;
}
