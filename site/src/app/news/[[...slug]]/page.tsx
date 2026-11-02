import type { Metadata } from 'next'
import Link from 'next/link'

import { AnnouncementSummary } from '@/components/AnnouncementSummary'
import { Prose } from '@/components/Prose'
import { Section } from '@/components/Section'
import {
  NEWS_SLUG,
  announcementAsPage,
  loadNewsLabels,
  loadPublishedAnnouncements,
} from '@/lib/announcements'
import type { Announcement } from '@/lib/announcements'
import { loadPage } from '@/lib/content'
import { buildPageMetadata } from '@/lib/page-metadata'
import { formatDate } from '@/lib/tournaments'

/**
 * /news/ and one page per announcement under it (v1-e37-t03), from one optional catch-all route.
 *
 * Two routes would be the obvious shape, but a static export refuses a dynamic route that
 * generates no page ("returned an empty array from generateStaticParams()"), and the site has
 * no published announcement between one expiring and the next being written. This route always
 * generates /news/ itself, so the export builds with none; any other path is a 404.
 */
export const dynamicParams = false

type Params = Promise<{ slug?: string[] }>

export function generateStaticParams(): Array<{ slug: string[] }> {
  return [
    { slug: [] },
    ...loadPublishedAnnouncements().map((announcement) => ({ slug: [announcement.slug] })),
  ]
}

/** The announcement a path names, or null for /news/ itself. */
function findAnnouncement(slug: string[] | undefined): Announcement | null {
  if (slug === undefined || slug.length === 0) {
    return null
  }
  const announcement = loadPublishedAnnouncements().find((candidate) => candidate.slug === slug.join('/'))
  if (!announcement) {
    throw new Error(`No published announcement at /${NEWS_SLUG}/${slug.join('/')}/ in content/announcements/`)
  }
  return announcement
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const announcement = findAnnouncement((await params).slug)
  return buildPageMetadata(announcement ? announcementAsPage(announcement) : loadPage(NEWS_SLUG))
}

/** The band holding the list. No announcement's anchor can match it: theirs start "announcement-". */
const NEWS_LIST_ID = 'news-list'

/**
 * Every announcement published on the build date, newest first, each linking to its own page. An
 * expired one is on no page, and one dated after the build date is not on it yet.
 */
function NewsList() {
  const page = loadPage(NEWS_SLUG)
  const labels = loadNewsLabels()
  const published = loadPublishedAnnouncements()

  return (
    <>
      <Section headingLevel={1} title={page.title}>
        <Prose html={page.html} />
      </Section>

      <Section id={NEWS_LIST_ID} tone="tinted">
        {published.length === 0 ? (
          <p className="announcement-empty">{labels.empty}</p>
        ) : (
          <ol className="announcement-list">
            {published.map((announcement) => (
              <li key={announcement.slug}>
                <AnnouncementSummary announcement={announcement} headingLevel={2} />
              </li>
            ))}
          </ol>
        )}
      </Section>
    </>
  )
}

/**
 * One announcement: its title, its date, its picture when it has one, and its body, rendered at
 * build time from Markdown that src/lib/announcements.ts has checked holds no HTML.
 */
function AnnouncementArticle({ announcement }: { announcement: Announcement }) {
  const labels = loadNewsLabels()

  return (
    <>
      <Section headingLevel={1} title={announcement.title}>
        <p className="announcement-date">
          <time dateTime={announcement.date}>{formatDate(announcement.date)}</time>
        </p>
      </Section>

      <Section>
        {announcement.image ? (
          <figure className="announcement-figure">
            {/* A plain <img>: the export has no image optimiser (next.config.ts), the file is
                served from this site's own public/ folder, and its path has a current consent
                entry or a nonPersonImages line, which the build checked. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img alt={announcement.image.alt} src={announcement.image.path} />
          </figure>
        ) : null}
        <Prose html={announcement.html} />
        <p className="announcement-back">
          <Link href={`/${NEWS_SLUG}/`} prefetch={false}>
            {labels.backToNews}
          </Link>
        </p>
      </Section>
    </>
  )
}

/**
 * Not one string below is written here. The list's title and opening come from
 * content/pages/news.md, the announcements from content/announcements/ and the words around them
 * from content/news.yaml, validated at build time; tests/announcements.test.tsx fails if a word
 * of that copy appears in this file.
 */
export default async function NewsRoute({ params }: { params: Params }) {
  const announcement = findAnnouncement((await params).slug)
  return announcement ? <AnnouncementArticle announcement={announcement} /> : <NewsList />
}
