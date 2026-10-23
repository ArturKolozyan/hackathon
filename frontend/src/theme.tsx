import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "rekeeper-theme";

function readTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function paint(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#FAF6EC" : "#0E0E0E");
}

type ThemeApi = {
  theme: Theme;
  toggle: () => void;
};

const ThemeContext = createContext<ThemeApi | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readTheme);

  const api = useMemo<ThemeApi>(
    () => ({
      theme,
      toggle() {
        const next: Theme = theme === "dark" ? "light" : "dark";
        paint(next);
        setTheme(next);
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
