import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { cleanup, render } from '@testing-library/react'
import { act } from 'react'
import { afterAll, describe, expect, it } from 'vitest'

import ContentPageRoute from '@/app/[slug]/page'
import HomePage from '@/app/page'
import { EmailUpdates } from '@/components/EmailUpdates'
import { SiteFrame } from '@/components/SiteFrame'
import type { EmailUpdatesContent } from '@/lib/content'
import {
  ContentValidationError,
  EMAIL_UPDATES_FILE,
  EMAIL_UPDATES_ID,
  loadEmailUpdatesContent,
  loadGuardedContent,
  loadPages,
  loadRoutedPages,
  loadSiteSettings,
} from '@/lib/content'
import { loadMediaConsent } from '@/lib/media-consent'
import { checkPublishingPolicy } from '@/lib/publishing-policy'

import { describeViolations, findAccessibilityViolations } from './axe'

/**
 * The parent email-updates section (v1-e37-t05 acceptance criteria 2 and 3).
 *
 * The section is one outbound link to the mailing service's hosted signup page, and everything
 * about it comes from content/email-updates.json. These tests hold the three properties that make
 * that safe: the link target is content, not code; the section can receive nothing, because it
 * has no form, no input and no script; and a signup section with nowhere to sign up cannot reach
 * prod. tests/no-third-party-scripts.test.ts checks the same things again over the built export.
 */

const settings = loadSiteSettings()
const navigationItems = loadPages().map((item) => ({ href: item.route, label: item.navLabel }))
const shipped = loadEmailUpdatesContent()
const rawShipped = JSON.parse(
  readFileSync(join(process.cwd(), 'content', EMAIL_UPDATES_FILE), 'utf8'),
) as Record<string, unknown>

/** The shipped copy with a real signup address, whatever state the shipped file is in. */
const WITH_LINK: EmailUpdatesContent = {
  ...shipped,
  signupUrl: 'https://mail.example.org/team-updates',
  placeholders: [],
}
const WITHOUT_LINK: EmailUpdatesContent = { ...shipped, signupUrl: null }

/** Every element that could hand a visitor's data to someone, or load someone else's code. */
const DATA_OR_CODE_ELEMENTS = 'form, input, textarea, select, button, script, iframe, img, object, embed'

async function flushPendingEffects() {
  await act(async () => {})
}

function renderInFrame(children: React.ReactNode) {
  return render(
    <SiteFrame items={navigationItems} strings={settings}>
      {children}
    </SiteFrame>,
    { container: document.body },
  )
}

const scratchDirectories: string[] = []

/** A content directory holding only email-updates.json, with `overrides` applied to the shipped file. */
function contentDirectoryWith(overrides: Record<string, unknown>): string {
  const directory = mkdtempSync(join(tmpdir(), 'email-updates-'))
  scratchDirectories.push(directory)
  writeFileSync(join(directory, EMAIL_UPDATES_FILE), JSON.stringify({ ...rawShipped, ...overrides }))
  return directory
}

afterAll(() => {
  for (const directory of scratchDirectories) rmSync(directory, { recursive: true, force: true })
})

describe('content/email-updates.json', () => {
  it('names the provider in every sentence that mentions it, with no token left over', () => {
    const text = [
      shipped.intro,
      ...shipped.points,
      shipped.action.label,
      shipped.action.externalLinkNote,
    ].join('\n')
    expect(text).not.toContain('{provider}')
    expect(text).toContain(shipped.providerName)
  })

  it('is written for parents and guardians, not students', () => {
    expect(shipped.title).toMatch(/parents and guardians/i)
    expect(JSON.stringify(rawShipped)).not.toMatch(/\bstudents? (?:can|may|should) sign up\b/i)
  })

  it('says in plain words that the address goes to the provider and not to this site', () => {
    const points = shipped.points.join(' ')
    expect(points).toContain(`Your address goes to ${shipped.providerName}, not to this site`)
    expect(points).toMatch(/confirm/i)
    expect(points).toMatch(/unsubscribe/i)
  })

  it('carries either an https signup page or the TBD marker, never anything else', () => {
    if (shipped.signupUrl === null) {
      expect(shipped.placeholders.join(' ')).toMatch(/signupUrl/)
    } else {
      expect(new URL(shipped.signupUrl).protocol).toBe('https:')
      expect(shipped.placeholders).toEqual([])
    }
  })

  it.each([
    ['plain http', 'http://mail.example.org/team'],
    ['a javascript: URL', 'javascript:alert(1)'],
    ['a relative path', '/signup/'],
    ['credentials in the URL', 'https://owner:secret@mail.example.org/team'],
    ['free text', 'ask a coach'],
  ])('refuses %s as the signup target', (_label, signupUrl) => {
    expect(() => loadEmailUpdatesContent(contentDirectoryWith({ signupUrl }))).toThrow(
      ContentValidationError,
    )
  })

  it('accepts an https signup page and reports no placeholder', () => {
    const content = loadEmailUpdatesContent(
      contentDirectoryWith({ signupUrl: 'https://mail.example.org/team' }),
    )
    expect(content.signupUrl).toBe('https://mail.example.org/team')
    expect(content.placeholders).toEqual([])
  })

  it('fills {provider} from providerName, so changing provider is a two-field edit', () => {
    const content = loadEmailUpdatesContent(
      contentDirectoryWith({ providerName: 'The District Messenger' }),
    )
    expect(content.points.join(' ')).toContain('Your address goes to The District Messenger')
    expect(content.action.externalLinkNote).toContain('The District Messenger')
    expect(content.signupUrl).toBe(shipped.signupUrl)
  })

  it('refuses any token other than {provider}', () => {
    expect(() =>
      loadEmailUpdatesContent(contentDirectoryWith({ intro: 'News from {team} by email.' })),
    ).toThrow(/the only token a sentence may use is \{provider\}/)
  })

  it('refuses a field it does not know, such as a form action', () => {
    expect(() =>
      loadEmailUpdatesContent(contentDirectoryWith({ formAction: 'https://mail.example.org/add' })),
    ).toThrow(ContentValidationError)
  })

  it('holds copy to house style: no em dash', () => {
    expect(() =>
      loadEmailUpdatesContent(contentDirectoryWith({ intro: 'Team news — by email.' })),
    ).toThrow(/em dash/)
  })
})

describe('the EmailUpdates section', () => {
  it('links to the signup page from content config, in the same tab, without a referrer', async () => {
    const { container } = renderInFrame(<EmailUpdates content={WITH_LINK} />)
    await flushPendingEffects()
    const section = container.querySelector(`#${EMAIL_UPDATES_ID}`) as HTMLElement
    const links = section.querySelectorAll('a')
    expect(links).toHaveLength(1)
    const link = links[0] as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe(WITH_LINK.signupUrl)
    expect(link.getAttribute('rel')?.split(' ')).toEqual(
      expect.arrayContaining(['noopener', 'noreferrer']),
    )
    expect(link.hasAttribute('target')).toBe(false)
  })

  it('says visibly that the link leaves the team site', async () => {
    const { container } = renderInFrame(<EmailUpdates content={WITH_LINK} />)
    await flushPendingEffects()
    const link = container.querySelector(`#${EMAIL_UPDATES_ID} a`) as HTMLAnchorElement
    expect(link.textContent).toBe(`${WITH_LINK.action.label} (${WITH_LINK.action.externalLinkNote})`)
    expect(link.querySelector('.visually-hidden, [hidden], [aria-hidden]')).toBeNull()
  })

  it('shows the heading, intro and every point from the config', async () => {
    const { container } = renderInFrame(<EmailUpdates content={WITH_LINK} />)
    await flushPendingEffects()
    const section = container.querySelector(`#${EMAIL_UPDATES_ID}`) as HTMLElement
    expect(section.querySelector('h2')?.textContent).toBe(WITH_LINK.title)
    expect(section.getAttribute('aria-labelledby')).toBe(`${EMAIL_UPDATES_ID}-title`)
    expect(section.textContent).toContain(WITH_LINK.intro)
    expect([...section.querySelectorAll('li')].map((item) => item.textContent)).toEqual(
      WITH_LINK.points,
    )
  })

  it('has no form, input, button, script, iframe or image: it can receive nothing', async () => {
    for (const content of [WITH_LINK, WITHOUT_LINK]) {
      const { container } = renderInFrame(<EmailUpdates content={content} />)
      await flushPendingEffects()
      const section = container.querySelector(`#${EMAIL_UPDATES_ID}`) as HTMLElement
      expect(section.querySelectorAll(DATA_OR_CODE_ELEMENTS)).toHaveLength(0)
      cleanup()
    }
  })

  it('shows the gap badge, and no link, while the signup address is still TBD', async () => {
    const { container } = renderInFrame(<EmailUpdates content={WITHOUT_LINK} />)
    await flushPendingEffects()
    const section = container.querySelector(`#${EMAIL_UPDATES_ID}`) as HTMLElement
    expect(section.querySelector('a')).toBeNull()
    expect(section.querySelector('.placeholder')?.textContent).toBe('TBD')
  })

  it('passes axe on the WCAG 2.1 A and AA rules', async () => {
    renderInFrame(<EmailUpdates content={WITH_LINK} />)
    await flushPendingEffects()
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toEqual([])
  })

  it('holds no copy of its own: every word comes from content/email-updates.json', () => {
    const source = readFileSync(join(process.cwd(), 'src/components/EmailUpdates.tsx'), 'utf8')
    for (const text of [shipped.title, shipped.intro, shipped.action.label, ...shipped.points]) {
      expect(source).not.toContain(text)
    }
    expect(source).not.toContain(shipped.providerName)
  })
})

describe('where the section appears', () => {
  it('is on the home page, directly after the season-schedule panel', async () => {
    const { container } = renderInFrame(<HomePage />)
    await flushPendingEffects()
    const ids = [...container.querySelectorAll('main > section')].map((section) => section.id)
    expect(ids).toContain(EMAIL_UPDATES_ID)
    expect(ids).toContain('season-schedule')
    expect(ids.indexOf(EMAIL_UPDATES_ID)).toBe(ids.indexOf('season-schedule') + 1)
  })

  it('is the last band of the contact page', async () => {
    const route = await ContentPageRoute({ params: Promise.resolve({ slug: 'contact' }) })
    const { container } = renderInFrame(route)
    await flushPendingEffects()
    const ids = [...container.querySelectorAll('main > section')].map((section) => section.id)
    expect(ids.at(-1)).toBe(EMAIL_UPDATES_ID)
  })

  it('is on no other Markdown page', async () => {
    for (const page of loadRoutedPages().filter((candidate) => candidate.slug !== 'contact')) {
      const route = await ContentPageRoute({ params: Promise.resolve({ slug: page.slug }) })
      const { container } = renderInFrame(route)
      await flushPendingEffects()
      expect(container.querySelector(`#${EMAIL_UPDATES_ID}`), page.filePath).toBeNull()
      cleanup()
    }
  })

  it('renders the shipped signup target on both pages', async () => {
    for (const element of [
      <HomePage key="home" />,
      await ContentPageRoute({ params: Promise.resolve({ slug: 'contact' }) }),
    ]) {
      const { container } = renderInFrame(element)
      await flushPendingEffects()
      const link = container.querySelector(`#${EMAIL_UPDATES_ID} a`)
      if (shipped.signupUrl === null) {
        expect(link).toBeNull()
      } else {
        expect(link?.getAttribute('href')).toBe(shipped.signupUrl)
      }
      cleanup()
    }
  })
})

describe('the publishing-policy guard', () => {
  const consent = loadMediaConsent()

  it('checks content/email-updates.json with the rest of the copy', () => {
    expect(loadGuardedContent().map((page) => page.filePath)).toContain(
      `content/${EMAIL_UPDATES_FILE}`,
    )
  })

  it('fails the build while the signup address is still TBD', () => {
    const directory = contentDirectoryWith({ signupUrl: '[[TBD: signup page]]' })
    const pages = loadGuardedContent().map((page) =>
      page.filePath === `content/${EMAIL_UPDATES_FILE}`
        ? { ...page, placeholders: loadEmailUpdatesContent(directory).placeholders }
        : page,
    )
    const messages = checkPublishingPolicy({ pages, settings, consent }).errors.map(
      (finding) => `${finding.location}: ${finding.message}`,
    )
    expect(messages.join('\n')).toMatch(
      /content\/email-updates\.json: still has an unfilled placeholder: signup page \(signupUrl\)/,
    )
  })
})
