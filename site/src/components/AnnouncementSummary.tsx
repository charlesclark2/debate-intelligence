import Link from 'next/link'

import type { Announcement } from '@/lib/announcements'
import { formatDate } from '@/lib/tournaments'

/**
 * One announcement in a list: its title, linking to its own page, its date, and the opening of
 * its body. The home page passes `pinnedLabel`, because there a pinned announcement sits above
 * newer ones and the label says why; /news/ is in date order and passes none.
 */
export function AnnouncementSummary({
  announcement,
  headingLevel,
  pinnedLabel,
}: {
  announcement: Announcement
  headingLevel: 2 | 3
  pinnedLabel?: string
}) {
  const Heading = `h${headingLevel}` as const
  const headingId = `announcement-${announcement.slug}-title`
  return (
    <article aria-labelledby={headingId} className="announcement-summary">
      <Heading className="announcement-summary__title" id={headingId}>
        <Link href={announcement.route} prefetch={false}>
          {announcement.title}
        </Link>
      </Heading>
      <p className="announcement-summary__meta">
        <time dateTime={announcement.date}>{formatDate(announcement.date)}</time>
        {pinnedLabel && announcement.pinned ? (
          <span className="announcement-summary__pinned">{pinnedLabel}</span>
        ) : null}
      </p>
      <p className="announcement-summary__summary">{announcement.summary}</p>
    </article>
  )
}
