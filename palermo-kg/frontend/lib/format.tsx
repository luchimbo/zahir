import { ReactNode } from "react";
import { Boxes, Building2, MapPin } from "lucide-react";

export function sourceHost(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "fuente";
  }
}

export function entityIcon(type: string) {
  if (type === "Organization") return <Building2 size={15} aria-hidden />;
  if (type === "Location") return <MapPin size={15} aria-hidden />;
  return <Boxes size={15} aria-hidden />;
}

export function inlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|\[\d+\])/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index === undefined) continue;
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${match.index}-b`}>{token.slice(2, -2)}</strong>);
    } else if (token.includes("](")) {
      const parsed = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (parsed) {
        nodes.push(
          <a key={`${match.index}-a`} href={parsed[2]} target="_blank" rel="noreferrer">
            {parsed[1]}
          </a>
        );
      }
    } else {
      nodes.push(<span key={`${match.index}-c`} className="citation-mark">{token}</span>);
    }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

export function renderMarkdown(markdown: string) {
  const blocks: ReactNode[] = [];
  const lines = markdown.split(/\r?\n/);
  let listItems: string[] = [];

  function flushList(key: string) {
    if (!listItems.length) return;
    blocks.push(
      <ul key={key}>
        {listItems.map((item, index) => (
          <li key={`${key}-${index}`}>{inlineMarkdown(item)}</li>
        ))}
      </ul>
    );
    listItems = [];
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList(`list-${index}`);
      return;
    }
    if (trimmed.startsWith("## ")) {
      flushList(`list-${index}`);
      blocks.push(<h2 key={index}>{inlineMarkdown(trimmed.slice(3))}</h2>);
      return;
    }
    if (trimmed.startsWith("### ")) {
      flushList(`list-${index}`);
      blocks.push(<h3 key={index}>{inlineMarkdown(trimmed.slice(4))}</h3>);
      return;
    }
    if (trimmed.startsWith("- ")) {
      listItems.push(trimmed.slice(2));
      return;
    }
    flushList(`list-${index}`);
    blocks.push(<p key={index}>{inlineMarkdown(trimmed)}</p>);
  });
  flushList("list-final");
  return blocks;
}
