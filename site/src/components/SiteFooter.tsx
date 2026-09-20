import Image from 'next/image'

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
 */
export function SiteFooter({ wordmark, note }: { wordmark: string; note: string }) {
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
      </div>
    </footer>
  )
}
