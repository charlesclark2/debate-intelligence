import type { Metadata } from 'next'
import { Fragment } from 'react'

import { Prose } from '@/components/Prose'
import { Section } from '@/components/Section'
import { loadPage, loadRoutedPages } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'

/** The band holding the at-a-glance block, when a page has one. */
const AT_A_GLANCE_ID = 'at-a-glance'

/**
 * One route per Markdown file in site/content/pages/, apart from the pages composed by a route
 * module of their own: home.md renders at the root, and the FAQ and the events page are built
 * from their YAML structure by src/app/faq/ and src/app/events/. See COMPOSED_SLUGS in
 * src/lib/content.ts, which is what keeps a static segment and this dynamic one from claiming the
 * same path.
 *
 * Adding an ordinary page to the site is still adding a file, not a component.
 */
export function generateStaticParams(): Array<{ slug: string }> {
  return loadRoutedPages().map((page) => ({ slug: page.slug }))
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>
}): Promise<Metadata> {
  const { slug } = await params
  return buildPageMetadata(loadPage(slug))
}

/**
 * A Markdown page, in up to three bands: the title and its lead, the at-a-glance block, then the
 * detail.
 *
 * Until v1-e36-t07 this was one column of prose with the title on top, which is how about, join,
 * coaches and contact each came to be a page a parent had to read from the beginning to find one
 * fact. The at-a-glance block is the fix at the scale these pages need: the handful of facts
 * somebody came for, as labels and values, before any of the prose that explains them. Both the
 * lead and that block are optional and come from the page's own front matter, so a page that
 * genuinely is one run of prose still renders correctly and Charlie adds a summary to a page by
 * editing the page, not this file.
 */
export default async function ContentPageRoute({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const page = loadPage(slug)

  return (
    <>
      <Section headingLevel={1} title={page.title}>
        {page.lead ? <p className="page-lead">{page.lead}</p> : null}
      </Section>

      {page.atAGlance ? (
        <Section id={AT_A_GLANCE_ID} title={page.atAGlance.title} tone="tinted">
          <dl className="at-a-glance">
            {page.atAGlance.items.map((item) => (
              <Fragment key={item.label}>
                <dt className="at-a-glance__label">{item.label}</dt>
                {/* The value is inline Markdown from the front matter, rendered at build time by
                    src/lib/content.ts, so an address or a link inside it behaves as it does
                    anywhere else in content/. */}
                <dd
                  className="at-a-glance__value"
                  dangerouslySetInnerHTML={{ __html: item.valueHtml }}
                />
              </Fragment>
            ))}
          </dl>
        </Section>
      ) : null}

      <Section>
        <Prose html={page.html} />
      </Section>
    </>
  )
}
