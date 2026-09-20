import type { ReactNode } from 'react'

/**
 * One question and its answer, as a native <details>/<summary> disclosure.
 *
 * WHY NATIVE, AND NOT A BUTTON WITH aria-expanded
 * -----------------------------------------------
 * The task spec forbids a hand-rolled accordion, and the reason is not purity. A browser's own
 * disclosure gives four things a scripted one has to reimplement and usually gets wrong:
 *
 *   - keyboard and screen-reader behaviour, including the expanded state, comes from the browser;
 *   - find-in-page reaches text inside a closed panel, and opens it (Chrome and Edge today,
 *     Firefox and Safari as they ship the same behaviour). Nothing is removed from the DOM;
 *   - printing can be made to show every answer with a stylesheet rule, because the content is
 *     there in the document rather than conditionally rendered;
 *   - it works with JavaScript switched off or still loading, which on a static site served from
 *     CloudFront is a real state a visitor can be in.
 *
 * That is also why this component is a server component with no state and no event handlers. It
 * ships no JavaScript at all: the whole interaction is the browser's.
 *
 * The question sits in a heading inside the <summary>, which the HTML content model allows
 * ("phrasing content, optionally intermixed with heading content"). It means a screen-reader user
 * can move through the questions with the heading shortcut instead of reading every panel, and it
 * keeps the page's outline unbroken: h1 page title, h2 topic, h3 question.
 *
 * The open and closed marker is drawn in CSS on the summary itself, so there is no extra element
 * to hide from a screen reader and nothing is fetched for it.
 */
export function Disclosure({
  children,
  headingLevel = 3,
  open = false,
  question,
}: {
  children: ReactNode
  headingLevel?: 2 | 3 | 4
  /**
   * Renders the `open` attribute. Reserved for the two or three most-asked questions: a page
   * where every panel is open is the wall of prose the disclosure replaced.
   */
  open?: boolean
  question: string
}) {
  const Heading = `h${headingLevel}` as const
  return (
    <details className="disclosure" open={open}>
      <summary className="disclosure__summary">
        <Heading className="disclosure__question">{question}</Heading>
      </summary>
      <div className="disclosure__panel">{children}</div>
    </details>
  )
}
