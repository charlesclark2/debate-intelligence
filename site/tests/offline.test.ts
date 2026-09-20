import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * The task spec forbids third-party scripts, trackers, analytics tags, remote fonts and CDN
 * assets, and forbids network access during lint, test and build. Those are properties of the
 * source, so they are checked by reading it: a reviewer should not have to watch a packet
 * capture to know the site stays offline.
 */

const ROOT = process.cwd()

function sourceFiles(directory: string, extensions: string[]): string[] {
  return readdirSync(join(ROOT, directory)).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(join(ROOT, path)).isDirectory()) {
      return sourceFiles(path, extensions)
    }
    return extensions.some((extension) => entry.endsWith(extension)) ? [path] : []
  })
}

const appSources = sourceFiles('src', ['.ts', '.tsx', '.css'])
const contentSources = sourceFiles('content', ['.md', '.yaml'])

function read(path: string): string {
  return readFileSync(join(ROOT, path), 'utf8')
}

describe('the site loads nothing from another company', () => {
  it('imports no web font', () => {
    for (const path of appSources) {
      expect(read(path), path).not.toMatch(/next\/font\/google/)
      expect(read(path), path).not.toMatch(/@import\s+url\(/)
      expect(read(path), path).not.toMatch(/fonts\.(googleapis|gstatic)\.com/)
    }
  })

  it('embeds no third-party script, tracker or analytics tag', () => {
    const forbidden = [
      /<script[^>]+src=["']https?:/i,
      /googletagmanager|google-analytics|gtag\(/i,
      /connect\.facebook\.net|platform\.twitter\.com/i,
      /cdn\.jsdelivr\.net|cdnjs\.cloudflare\.com|unpkg\.com/i,
    ]
    for (const path of appSources) {
      const source = read(path)
      for (const pattern of forbidden) {
        expect(source, `${path} matches ${pattern}`).not.toMatch(pattern)
      }
    }
  })

  it('makes no request of its own at runtime', () => {
    for (const path of appSources) {
      expect(read(path), path).not.toMatch(/\bfetch\s*\(/)
      expect(read(path), path).not.toMatch(/XMLHttpRequest|navigator\.sendBeacon/)
    }
  })

  it('references images only from the site itself', () => {
    const remoteImage = /(?:src|href)=["']https?:\/\//i
    for (const path of [...appSources, ...contentSources]) {
      expect(read(path), path).not.toMatch(remoteImage)
    }
  })
})

describe('the build stays offline', () => {
  const packageJson = JSON.parse(read('package.json')) as {
    scripts: Record<string, string>
  }

  it('turns off Next telemetry, which would otherwise report each build', () => {
    expect(packageJson.scripts.build).toContain('NEXT_TELEMETRY_DISABLED=1')
    expect(packageJson.scripts.dev).toContain('NEXT_TELEMETRY_DISABLED=1')
  })

  it('configures a static export with no server runtime', () => {
    const config = read('next.config.ts')
    expect(config).toContain("output: 'export'")
    expect(config).toContain('trailingSlash: true')
    expect(config).toContain('unoptimized: true')
  })

  it('uses no Next feature that a static export cannot serve', () => {
    const serverOnly = [/from ['"]next\/server['"]/, /export async function (GET|POST)\b/]
    for (const path of appSources) {
      for (const pattern of serverOnly) {
        expect(read(path), `${path} matches ${pattern}`).not.toMatch(pattern)
      }
    }
    expect(sourceFiles('src', ['.ts', '.tsx'])).not.toContain('src/middleware.ts')
  })

  it('keeps the site independent of the V2 app in web/', () => {
    for (const path of appSources) {
      expect(read(path), path).not.toMatch(/from ['"][^'"]*\bweb\//)
    }
    const manifest = JSON.parse(read('package.json')) as {
      dependencies: Record<string, string>
      devDependencies: Record<string, string>
    }
    for (const version of Object.values({ ...manifest.dependencies, ...manifest.devDependencies })) {
      expect(version).not.toMatch(/^(link|file|workspace):/)
    }
  })
})
