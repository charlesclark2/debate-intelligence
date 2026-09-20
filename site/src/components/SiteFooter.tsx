/**
 * The contentinfo landmark.
 *
 * The footer sits on brand navy. The "W BAY" mark is an opaque white-background PNG, so putting
 * it here would show a white box; until a transparent PNG or SVG exists the footer uses the
 * wordmark as text instead. See site/README.md and the follow-up work in the session report.
 */
export function SiteFooter({ wordmark, note }: { wordmark: string; note: string }) {
  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <p className="site-footer__wordmark">{wordmark}</p>
        <p className="site-footer__note">{note}</p>
      </div>
    </footer>
  )
}
