import type { Metadata } from 'next'

import { Disclosure } from '@/components/Disclosure'
import { Prose } from '@/components/Prose'
import { Section } from '@/components/Section'
import { FAQ_SLUG, loadFaqContent, loadPage } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'

/** The band holding the in-page topic index, and the anchor its heading gives the nav its name from. */
const TOPIC_INDEX_ID = 'faq-topics'

export function generateMetadata(): Metadata {
  return buildPageMetadata(loadPage(FAQ_SLUG))
}

/**
 * The parent FAQ.
 *
 * Sixteen questions used to be sixteen <h2> headings and about a thousand words of prose in one
 * column, which a parent looking for the cost of a season had to read past. The same sixteen
 * questions are now five topics, each question a native disclosure, and the three most-asked ones
 * open on arrival. The topic index above them is the five-second version: a parent reads five
 * labels, presses one, and is at their answer.
 *
 * Nothing here decides what any of that says. The title and the lead come from
 * content/pages/faq.md and every question, answer and topic label from content/faq.yaml, both read
 * through src/lib/content.ts and validated at build time; tests/faq.test.tsx fails if a word of
 * that copy appears in this file.
 *
 * No JavaScript is shipped for the disclosures. See src/components/Disclosure.tsx for why they are
 * the browser's own <details> rather than a scripted accordion.
 */
export default function FaqPage() {
  const page = loadPage(FAQ_SLUG)
  const { closing, indexTitle, groups } = loadFaqContent()

  return (
    <>
      <Section headingLevel={1} title={page.title}>
        <Prose html={page.html} />
      </Section>

      <Section id={TOPIC_INDEX_ID} title={indexTitle} tone="tinted">
        {/* Labelled by the band's own heading, so a screen reader moving between navigation
            landmarks hears this region's own name rather than a second unnamed "navigation". */}
        <nav aria-labelledby={`${TOPIC_INDEX_ID}-title`} className="topic-index">
          <ul className="topic-index__list">
            {groups.map((group) => (
              <li key={group.id}>
                <a className="topic-index__link" href={`#${group.id}`}>
                  {group.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </Section>

      {groups.map((group) => (
        <Section id={group.id} key={group.id} title={group.label}>
          {group.questions.map((question) => (
            <Disclosure
              key={question.question}
              open={question.openByDefault}
              question={question.question}
            >
              <Prose html={question.answerHtml} />
            </Disclosure>
          ))}
        </Section>
      ))}

      {/* The way out of the page, at the foot of it: a parent who has read the topics and not
          found their question is looking here, not at the top. */}
      <Section id="ask-a-question" title={closing.title} tone="tinted">
        <Prose html={closing.bodyHtml} />
      </Section>
    </>
  )
}
