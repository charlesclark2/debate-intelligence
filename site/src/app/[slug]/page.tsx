import type { Metadata } from 'next'

import { Prose } from '@/components/Prose'
import { loadPage, loadRoutedPages } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'

/**
 * One route per Markdown file in site/content/pages/, apart from home.md which renders at the
 * root. Adding a page to the site means adding a file, not a component: that is what task
 * v1-e36-t04 does with the core pages for parents and students.
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
    <>
      <h1>{page.title}</h1>
      <Prose html={page.html} />
    </>
  )
}
