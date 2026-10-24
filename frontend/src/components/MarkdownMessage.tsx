import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toStructuredMarkdown } from "../markdown";

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

export function MarkdownMessage({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
        {toStructuredMarkdown(text)}
      </ReactMarkdown>
    </div>
  );
}
