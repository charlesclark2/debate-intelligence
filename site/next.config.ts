import type { NextConfig } from 'next'

/**
 * The public team site is a pure static export: `next build` writes plain files to site/out/,
 * which the S3 + CloudFront distribution from v1-e36-t02 serves directly. Nothing here may
 * depend on a Node server at request time — no API routes, middleware, server actions or ISR.
 *
 * - `output: 'export'`      static HTML/CSS/JS only, no server runtime.
 * - `trailingSlash: true`   every route becomes `<route>/index.html`, which is what CloudFront's
 *                           default-root-object behaviour expects for sub-paths.
 * - `images.unoptimized`    the Next image optimiser needs a server; images ship as-is.
 * - `agentRules: false`     `next dev` otherwise writes an AGENTS.md and a CLAUDE.md into site/
 *                           on first run. A CLAUDE.md there would shadow the repository guide at
 *                           the root for any session working in this directory, so the generator
 *                           is off and the guidance stays in one place.
 */
const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  reactStrictMode: true,
  agentRules: false,
}

export default nextConfig
