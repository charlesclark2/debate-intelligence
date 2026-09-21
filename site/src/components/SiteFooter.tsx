import Image from 'next/image'
import Link from 'next/link'

import type { NavigationItem } from './SiteNav'

/**
 * The contentinfo landmark.
 *
 * The footer sits on brand navy, so it uses the white knockout version of the "W BAY" mark. It is
 * a transparent PNG, which is why the mark can go here at all: the opaque assets the scaffold
 * shipped with would have shown a white box, and the footer used a text wordmark instead.
 *
 * The mark is decorative here. It repeats the header's link home and carries no information of
 * its own, so its alt text is empty and a screen reader skips it, and the team name is still in
 * the note beside it.
 *
 * It also carries the utility links (v1-e36-t07). The accessibility statement used to sit in the
 * header nav beside Contact, because the nav was every file in content/pages/ and that statement
 * is a file. It belongs here: a parent deciding whether their child joins is not looking for it,
 * and someone who needs it knows to look in a footer. Anything published and not named in
 * content/site.yaml's primaryNavigation arrives here, so leaving a page out of the nav moves it
 * rather than hiding it.
 */
export function SiteFooter({
  navigationLabel,
  note,
  utilityLinks,
  wordmark,
}: {
  navigationLabel: string
  note: string
  utilityLinks: NavigationItem[]
  wordmark: string
}) {
  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <Image
          alt=""
          className="site-footer__mark"
          height={264}
          src="/brand/wfb-mark-white-knockout.png"
          width={441}
        />
        <p className="site-footer__wordmark">{wordmark}</p>
        <p className="site-footer__note">{note}</p>
        {utilityLinks.length > 0 ? (
          <nav aria-label={navigationLabel} className="site-footer__nav">
            <ul className="site-footer__links">
              {utilityLinks.map((link) => (
                <li key={link.href}>
                  <Link className="site-footer__link" href={link.href} prefetch={false}>
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}
      </div>
    </footer>
  )
}
