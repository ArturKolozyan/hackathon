import { Link } from "react-router-dom";
import { useTheme } from "../theme";

export function Wordmark({ to }: { to?: string }) {
  const { theme } = useTheme();
  const src = theme === "light" ? "/brand/rekeeper-light.svg" : "/brand/rekeeper-dark.svg";
  const image = <img src={src} alt="rekeeper" />;
  if (to) {
    return (
      <Link to={to} className="wordmark">
        {image}
      </Link>
    );
  }
  return <span className="wordmark">{image}</span>;
}

export function TeamMark() {
  return <p className="team-mark">404 mercy</p>;
}

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const toLight = theme === "dark";
  return (
    <button
      type="button"
      className="icon-btn"
      onClick={toggle}
      aria-pressed={theme === "light"}
      aria-label={toLight ? "Светлая тема" : "Тёмная тема"}
      title={toLight ? "Светлая тема" : "Тёмная тема"}
    >
      {toLight ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        d="M16 3.2A8.5 8.5 0 1 0 20.8 15 7 7 0 0 1 16 3.2Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}
