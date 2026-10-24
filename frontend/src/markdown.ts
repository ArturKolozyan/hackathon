const MARKDOWN_HINT = /(^|\n)\s{0,3}(#{1,6}\s|[-*]\s|\d+\.\s)|\*\*|^\s*\|.+\|/m;

const GROUPS = new Set(["Просрочено", "Скоро", "Впереди", "Оплачено", "Прочее"]);
const ITEM_LINE = /^\*\*(.+?)\*\*\s+[—–-]\s+(.+)$/;
const META_LINE = /^до\s+(\d{2}\.\d{2}\.\d{4}),\s+(.+?),\s+ответственный:\s+(.+)$/;

export type AssistantBlock =
  | { kind: "md"; text: string }
  | { kind: "group"; label: string }
  | { kind: "pay"; name: string; amount: string; due: string; status: string; person: string };

/** Pull compact payment rows out of tool markdown. Other text stays a markdown chunk. */
export function splitAssistantBlocks(source: string): AssistantBlock[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: AssistantBlock[] = [];
  const buf: string[] = [];
  const flush = () => {
    const text = buf.join("\n").trim();
    buf.length = 0;
    if (text) blocks.push({ kind: "md", text });
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trim();
    if (GROUPS.has(line)) {
      flush();
      blocks.push({ kind: "group", label: line });
      continue;
    }
    const item = line.match(ITEM_LINE);
    const meta = lines[index + 1]?.trim().match(META_LINE);
    if (item && meta) {
      flush();
      blocks.push({
        kind: "pay",
        name: item[1],
        amount: item[2],
        due: meta[1],
        status: meta[2].trim(),
        person: meta[3].trim(),
      });
      index += 1;
      continue;
    }
    buf.push(lines[index]);
  }
  flush();
  return blocks;
}

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
    const heading = line.endsWith(":") && line.length <= 90;
    if (heading) {
      out.push("", `**${line.slice(0, -1)}**`, "");
      continue;
    }
    out.push(line, "");
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
