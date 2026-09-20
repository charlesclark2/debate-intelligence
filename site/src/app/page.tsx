import type { Metadata } from 'next'

import { Prose } from '@/components/Prose'
import { HOME_SLUG, loadPage } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'

export function generateMetadata(): Metadata {
  return buildPageMetadata(loadPage(HOME_SLUG))
}

export default function HomePage() {
  const page = loadPage(HOME_SLUG)
  return (
    <>
      <h1>{page.title}</h1>
      <Prose html={page.html} />
    </>
  )
}
