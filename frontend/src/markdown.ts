const MARKDOWN_HINT = /(^|\n)\s{0,3}(#{1,6}\s|[-*]\s|\d+\.\s)|\*\*|^\s*\|.+\|/m;

/** Plain tool text becomes short markdown: a heading line and bullets. Text that is already markdown passes through. */
export function toStructuredMarkdown(source: string): string {
  const text = source.replace(/\r\n/g, "\n").trim();
  if (!text || MARKDOWN_HINT.test(text)) return text;
  const out: string[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) {
      out.push("");
      continue;
    }
    const heading = line.endsWith(":") && line.length <= 90 && !line.includes("·");
    if (heading) {
      out.push("", `**${line.slice(0, -1)}**`, "");
      continue;
    }
    if (line.includes(" · ")) {
      out.push(`- ${line}`);
      continue;
    }
    out.push(line, "");
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
