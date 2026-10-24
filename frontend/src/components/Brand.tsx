import { Moon, Sun } from "lucide-react";
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
  return <p className="team-mark">404 mercy not found</p>;
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
      {toLight ? <Sun size={18} strokeWidth={1.75} aria-hidden /> : <Moon size={18} strokeWidth={1.75} aria-hidden />}
    </button>
  );
}
