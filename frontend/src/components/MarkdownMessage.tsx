import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { splitAssistantBlocks, toStructuredMarkdown, type AssistantBlock } from "../markdown";

const SAFE_LINK = /^https?:\/\//i;

const components: Components = {
  a: ({ href, children }) => {
    if (!href || !SAFE_LINK.test(href)) return <span>{children}</span>;
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    );
  },
  table: ({ children }) => (
    <div className="md-scroll">
      <table>{children}</table>
    </div>
  ),
};

const PILL: Record<string, [string, string]> = {
  просрочено: ["pill-overdue", "Просрочено"],
  скоро: ["pill-soon", "Скоро"],
  впереди: ["pill-neutral", "Впереди"],
  оплачено: ["pill-paid", "Оплачено"],
};

function MarkdownChunk({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
      {toStructuredMarkdown(text)}
    </ReactMarkdown>
  );
}

function PayRow({ block }: { block: Extract<AssistantBlock, { kind: "pay" }> }) {
  const pill = PILL[block.status] ?? ["pill-neutral", block.status];
  return (
    <div className="pay-row">
      <div className="pay-top">
        <strong>{block.name}</strong>
        <span className="pay-amt">{block.amount}</span>
      </div>
      <div className="pay-meta">
        <span>до {block.due}</span>
        <span className={`pill ${pill[0]}`}>{pill[1]}</span>
        <span>{block.person}</span>
      </div>
    </div>
  );
}

export function MarkdownMessage({ text }: { text: string }) {
  const blocks = splitAssistantBlocks(text);
  return (
    <div className="md">
      {blocks.map((block, index) => {
        if (block.kind === "group") return <p key={index} className="pay-group">{block.label}</p>;
        if (block.kind === "pay") return <PayRow key={index} block={block} />;
        return <MarkdownChunk key={index} text={block.text} />;
      })}
    </div>
  );
}
