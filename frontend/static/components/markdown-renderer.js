/** Safe Markdown projection shared by historical and streamed Agent messages. */
import { marked } from "../vendor/marked/marked.esm.js";
import DOMPurify from "../vendor/dompurify/purify.es.mjs";

const MARKDOWN_SANITIZE_OPTIONS = Object.freeze({
  ALLOWED_TAGS: [
    "a", "blockquote", "br", "code", "del", "details", "div", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "kbd", "li",
    "ol", "p", "pre", "s", "span", "strong", "summary", "table",
    "tbody", "td", "th", "thead", "tr", "ul",
  ],
  ALLOWED_ATTR: ["class", "colspan", "href", "start", "title"],
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
  FORBID_ATTR: ["style"],
});

/**
 * Return whether a sanitized Markdown link uses one browser-safe protocol.
 *
 * Args:
 *   href: Link destination retained by the sanitizer.
 *
 * Returns:
 *   Whether the destination is an HTTP(S) page or an email link.
 */
function isAllowedLink(href) {
  try {
    return ["http:", "https:", "mailto:"].includes(new URL(href).protocol);
  } catch {
    return false;
  }
}

/**
 * Parse Agent Markdown and remove every executable or style-bearing HTML path.
 *
 * Args:
 *   source: Untrusted model text retained as the durable message source.
 *
 * Returns:
 *   Sanitized HTML suitable only for insertion into a host-owned message body.
 */
export function renderMarkdown(source) {
  const parsed = marked.parse(String(source ?? ""), {
    breaks: true,
    gfm: true,
  });
  return DOMPurify.sanitize(parsed, MARKDOWN_SANITIZE_OPTIONS);
}

/**
 * Replace one host-owned element with the safe Markdown projection of raw text.
 *
 * Args:
 *   target: Existing message-body element owned by the workbench.
 *   source: Untrusted Markdown source to project into the element.
 *
 * Returns:
 *   None. The target receives only sanitized parser output.
 */
export function renderMarkdownInto(target, source) {
  target.innerHTML = renderMarkdown(source);
  for (const anchor of target.querySelectorAll("a[href]")) {
    if (!isAllowedLink(anchor.href)) {
      anchor.removeAttribute("href");
      continue;
    }
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
  }
}

/**
 * Create an animation-frame-batched renderer for one streaming message field.
 *
 * Args:
 *   target: Existing message body that receives the safe Markdown projection.
 *   afterRender: Optional host callback invoked after a scheduled update.
 *
 * Returns:
 *   Mutable stream view accepting raw cumulative content and a final flush.
 */
export function createMarkdownStream(target, afterRender = () => {}) {
  let source = "";
  let frame = 0;
  let disposed = false;

  function flush() {
    frame = 0;
    if (disposed) return;
    renderMarkdownInto(target, source);
    afterRender();
  }

  return {
    /**
     * Schedule one latest-value Markdown projection for the next frame.
     *
     * Args:
     *   nextSource: Complete accumulated raw text received so far.
     *
     * Returns:
     *   None. Earlier queued values are coalesced into the latest source.
     */
    update(nextSource) {
      source = String(nextSource ?? "");
      if (!frame && !disposed) frame = requestAnimationFrame(flush);
    },

    /**
     * Immediately project the latest source, including terminal stream text.
     *
     * Returns:
     *   None. A pending animation-frame update is cancelled first.
     */
    flush() {
      if (frame) cancelAnimationFrame(frame);
      flush();
    },

    /**
     * Stop pending rendering after the owning message card is removed.
     *
     * Returns:
     *   None. No future DOM mutation occurs for this stream view.
     */
    dispose() {
      disposed = true;
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
    },
  };
}
