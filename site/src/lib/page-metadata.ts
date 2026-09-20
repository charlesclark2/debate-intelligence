import type { Metadata } from 'next'

import type { ContentPage } from './content'
import { loadSiteSettings } from './content'
import { absoluteUrl, isIndexable } from './site-settings'

/**
 * Builds the Next metadata object for one content page: title and description from the file's
 * front matter, a canonical URL and Open Graph tags from SITE_URL, and the indexing directive
 * from SITE_ENV. A dev build emits `noindex, nofollow` on every page, which together with the
 * disallow-everything robots.txt keeps previews out of search results.
 */
export function buildPageMetadata(
  page: ContentPage,
  contentDirectory?: string,
  env: NodeJS.ProcessEnv = process.env,
): Metadata {
  const settings = loadSiteSettings(contentDirectory)
  const indexable = isIndexable(env)
  const url = absoluteUrl(page.route, env)

  return {
    title: page.title,
    description: page.description,
    alternates: { canonical: url },
    robots: {
      index: indexable,
      follow: indexable,
    },
    openGraph: {
      type: 'website',
      siteName: settings.name,
      title: page.title,
      description: page.description,
      url,
      ...(page.openGraphImage ? { images: [{ url: absoluteUrl(page.openGraphImage, env) }] } : {}),
    },
  }
}
