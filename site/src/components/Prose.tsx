/**
 * Renders one content file's Markdown. The HTML comes from src/lib/content.ts, which converts
 * Markdown committed in this repository at build time; nothing user-supplied reaches this
 * component, and no HTML is ever fetched or injected at runtime.
 */
export function Prose({ html }: { html: string }) {
  return <div className="prose" dangerouslySetInnerHTML={{ __html: html }} />
}
