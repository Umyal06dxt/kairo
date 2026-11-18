import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "home" | "chat" | "mic" | "lab" | "menu" | "back" | "close" | "play" | "pause" | "sparkle"
  | "settings" | "send" | "stop" | "check" | "chart" | "book" | "arrow";

const PATHS: Record<IconName, ReactNode> = {
  home: <path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4v-5H9v5H5a1 1 0 0 1-1-1z" />,
  chat: <path d="M5 6h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-7l-4 3.5V16H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z" />,
  mic: (<><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" /></>),
  lab: (<><circle cx="7" cy="7" r="2.4" /><circle cx="17" cy="7" r="2.4" /><circle cx="7" cy="17" r="2.4" /><circle cx="17" cy="17" r="2.4" /></>),
  menu: <path d="M5 8h14M5 12h14M5 16h14" />,
  back: <path d="m14.5 6-6 6 6 6" />,
  close: <path d="m6.5 6.5 11 11m0-11-11 11" />,
  play: <path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none" />,
  pause: (<><rect x="7" y="5.5" width="3.6" height="13" rx="1" fill="currentColor" stroke="none" /><rect x="13.4" y="5.5" width="3.6" height="13" rx="1" fill="currentColor" stroke="none" /></>),
  sparkle: <path d="M12 4v5M12 15v5M4 12h5M15 12h5M7 7l2.5 2.5M14.5 14.5 17 17M17 7l-2.5 2.5M9.5 14.5 7 17" />,
  settings: (<><circle cx="12" cy="12" r="3" /><path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6 6l1.6 1.6M16.4 16.4 18 18M18 6l-1.6 1.6M7.6 16.4 6 18" /></>),
  send: <path d="M5 12 19 5l-4.5 14-3-5.5z" />,
  stop: <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" />,
  check: <path d="m5.5 12.5 4 4 9-9" />,
  chart: <path d="M5 19V9m5 10V5m5 14v-7m5 7V8" />,
  book: <path d="M5 5.5A1.5 1.5 0 0 1 6.5 4H19v14H6.5A1.5 1.5 0 0 0 5 19.5zM5 19.5A1.5 1.5 0 0 0 6.5 21H19" />,
  arrow: <path d="M8 6l6 6-6 6" />,
};

interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> { name: IconName; size?: number }

/** Decorative by default (aria-hidden); wrap in a labelled button for meaning. */
export function Icon({ name, size = 22, ...rest }: IconProps) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}
