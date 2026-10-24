import type { ReactNode } from "react";
import { TeamMark, ThemeSwitch, Wordmark } from "./Brand";

export function AuthFrame({ kicker, title, text, children }: { kicker: string; title: string; text: string; children: ReactNode }) {
  return (
    <div className="login-page">
      <header className="topbar">
        <Wordmark />
        <ThemeSwitch />
      </header>
      <div className="login-grid">
        <section className="login-copy">
          <p className="kicker">{kicker}</p>
          <h1>{title}</h1>
          <p>{text}</p>
        </section>
        {children}
      </div>
      <footer className="login-foot">
        <TeamMark />
      </footer>
    </div>
  );
}
