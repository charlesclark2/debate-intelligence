import { Prose } from '@/components/Prose'
import { loadNotFoundPage } from '@/lib/content'

/**
 * Exported as out/404.html, which CloudFront serves as the custom error response (v1-e36-t02).
 */
export default function NotFoundPage() {
  const page = loadNotFoundPage()
  return (
    <>
      <h1>{page.title}</h1>
      <Prose html={page.html} />
    </>
  )
}
