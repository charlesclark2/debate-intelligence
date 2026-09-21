import type { MetadataRoute } from 'next'

import { loadPages } from '@/lib/content'
import { absoluteUrl } from '@/lib/site-settings'

export const dynamic = 'force-static'

/**
 * Every published content page, in navigation order. `lastModified` is deliberately left out:
 * it would be read from file timestamps, which differ between checkouts and would make the
 * static export non-reproducible.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  return loadPages().map((page) => ({
    url: absoluteUrl(page.route),
    changeFrequency: 'monthly' as const,
    priority: page.route === '/' ? 1 : 0.7,
  }))
}
