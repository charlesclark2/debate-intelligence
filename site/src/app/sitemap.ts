import type { MetadataRoute } from 'next'

import { loadPublishedAnnouncements } from '@/lib/announcements'
import { loadPages } from '@/lib/content'
import { absoluteUrl } from '@/lib/site-settings'

export const dynamic = 'force-static'

/**
 * Every published content page, in navigation order, then every announcement published on the
 * build date, newest first: an expired one is in no sitemap (v1-e37-t03). `lastModified` is
 * deliberately left out:
 * it would be read from file timestamps, which differ between checkouts and would make the
 * static export non-reproducible.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    ...loadPages().map((page) => ({
      url: absoluteUrl(page.route),
      changeFrequency: 'monthly' as const,
      priority: page.route === '/' ? 1 : 0.7,
    })),
    ...loadPublishedAnnouncements().map((announcement) => ({
      url: absoluteUrl(announcement.route),
      changeFrequency: 'weekly' as const,
      priority: 0.5,
    })),
  ]
}
