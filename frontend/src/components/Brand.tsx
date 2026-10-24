import { Moon, Sun } from "lucide-react";
import { Link } from "react-router-dom";
import { HINTS } from "../hints";
import { THEMES, useTheme, type Theme } from "../theme";

export function Wordmark({ to }: { to?: string }) {
  const { theme } = useTheme();
  // Ссылка-логотип живёт в сайдбаре; в «Аезе» он голубой, и «re» там белое.
  const src =
    theme === "dark" ? "/brand/rekeeper-dark.svg" : theme === "aeza" && to ? "/brand/rekeeper-aeza.svg" : "/brand/rekeeper-light.svg";
  const image = <img src={src} alt="rekeeper" />;
  if (to) {
    return (
      <Link to={to} className="wordmark" data-hint={HINTS.logo}>
        {image}
      </Link>
    );
  }
  return <span className="wordmark">{image}</span>;
}

export function TeamMark() {
  return <p className="team-mark">404 mercy not found</p>;
}

/** Знак é в клавише (брендбук Aéza, слайд 10). Только цвет текста: чёрный или белый, без перекраски. */
function AezaKey() {
  return (
    <svg viewBox="0 0 348.23 348.23" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M 87.06 0 L 261.18 0 C 309.26 0 348.23 38.98 348.23 87.06 L 348.23 261.18 C 348.23 309.26 309.26 348.23 261.18 348.23 L 87.06 348.23 C 38.98 348.23 0 309.26 0 261.18 L 0 87.06 C 0 38.98 38.98 0 87.06 0 M 177.5 36.62 L 154.85 85.09 L 187.03 85.09 L 219.52 36.62 Z M 177.5 36.62 M 139.02 169.93 C 139.22 164.21 140.65 159.01 143.3 154.42 C 146.27 149.21 150.24 145.13 155.24 142.17 C 160.45 139.01 166.37 137.48 173 137.48 C 179.32 137.48 184.94 138.91 189.73 141.77 C 194.63 144.42 198.41 148.3 201.16 153.19 C 203.92 157.99 205.24 163.6 205.24 169.93 Z M 246.57 185.03 C 246.57 171.56 244.63 159.83 240.86 149.83 C 237.08 139.72 231.88 131.36 225.04 124.72 C 218.3 118.09 210.45 113.09 201.37 109.82 C 192.39 106.46 182.69 104.82 172.29 104.82 C 156.77 104.82 147.9 108.7 135.96 116.05 C 124.53 122.99 117.49 131.15 111.16 143.5 C 104.84 155.75 101.67 170.03 101.67 186.25 C 101.67 202.99 104.84 217.38 111.16 229.62 C 117.49 241.77 126.16 251.05 137.8 257.68 C 148.61 263.4 157.79 267.99 174.02 267.99 C 187.08 267.99 197.29 266.46 207.18 262.48 C 217.29 258.5 225.04 252.48 231.37 245.34 C 237.7 238.09 241.68 226.77 243.2 217.07 L 206.88 217.07 C 205.45 221.05 202.49 225.34 199.53 228.09 C 196.67 230.85 193.2 232.89 189.22 234.32 C 185.14 235.64 180.65 236.36 175.75 236.36 C 168.51 236.36 161.06 233.71 155.65 230.64 C 150.35 227.58 146.16 223.2 143.2 217.48 C 140.65 212.48 139.32 206.66 139.02 199.93 L 246.57 199.93 Z M 246.57 185.03"
      />
    </svg>
  );
}

const THEME_LABEL: Record<Theme, string> = { light: "Светлая тема", dark: "Тёмная тема", aeza: "Тема «Аеза»" };
const THEME_HINT: Record<Theme, string> = {
  light: HINTS.themeLight,
  dark: HINTS.themeDark,
  aeza: HINTS.themeAeza,
};

/** Три темы рядом: солнце, луна и клавиша é. Выбранная отмечена фоном кнопки. */
export function ThemeSwitch() {
  const { theme, setTheme } = useTheme();
  return (
    <div className="theme-switch" role="group" aria-label="Тема оформления">
      {THEMES.map((option) => (
        <button
          key={option}
          type="button"
          className="theme-option"
          aria-pressed={theme === option}
          aria-label={THEME_LABEL[option]}
          data-hint={THEME_HINT[option]}
          onClick={() => setTheme(option)}
        >
          {option === "light" ? (
            <Sun size={18} strokeWidth={1.75} aria-hidden />
          ) : option === "dark" ? (
            <Moon size={18} strokeWidth={1.75} aria-hidden />
          ) : (
            <AezaKey />
          )}
        </button>
      ))}
    </div>
  );
}
