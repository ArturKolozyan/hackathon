import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type Theme = "dark" | "light" | "aeza";

export const THEMES: Theme[] = ["light", "dark", "aeza"];

const STORAGE_KEY = "rekeeper-theme";
const BROWSER_BAR: Record<Theme, string> = { dark: "#0E0E0E", light: "#FAF6EC", aeza: "#F4F4F4" };

function readTheme(): Theme {
  const current = document.documentElement.dataset.theme;
  return current === "light" || current === "aeza" ? current : "dark";
}

function paint(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", BROWSER_BAR[theme]);
}

type ThemeApi = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeApi | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setState] = useState<Theme>(readTheme);

  const api = useMemo<ThemeApi>(
    () => ({
      theme,
      setTheme(next) {
        paint(next);
        setState(next);
      },
    }),
    [theme],
  );

  return <ThemeContext.Provider value={api}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeApi {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("ThemeProvider отсутствует");
  return value;
}
