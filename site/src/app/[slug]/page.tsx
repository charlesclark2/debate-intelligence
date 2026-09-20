import type { Metadata } from 'next'

import { Prose } from '@/components/Prose'
import { loadPage, loadRoutedPages } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'

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

export default async function ContentPageRoute({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const page = loadPage(slug)
  return (
    <div className="page-column">
      <h1>{page.title}</h1>
      <Prose html={page.html} />
    </div>
  )
}
