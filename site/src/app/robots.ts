import type { MetadataRoute } from 'next'

import { absoluteUrl, isIndexable } from '@/lib/site-settings'

export const dynamic = 'force-static'

/**
 * SITE_ENV decides this file. A dev build (or any build with SITE_ENV unset or unrecognised)
 * disallows every path, so the CloudFront preview distribution from v1-e36-t02 is never indexed;
 * only a prod build invites crawlers and advertises the sitemap.
 */
export default function robots(): MetadataRoute.Robots {
  if (!isIndexable()) {
    return {
      rules: [{ userAgent: '*', disallow: '/' }],
    }
  }
  return {
    rules: [{ userAgent: '*', allow: '/' }],
    sitemap: absoluteUrl('/sitemap.xml'),
  }
}
