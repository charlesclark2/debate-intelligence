import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

import { EMAIL_UPDATES_ID, loadEmailUpdatesContent, loadSiteSettings } from '@/lib/content'

import { exportDirectory as outDirectory } from './built-export'

/**
 * The built site loads nothing from the mailing provider, or from anyone else, and has nothing
 * that could take a visitor's address (v1-e37-t05 acceptance criteria 2 and 3).
 *
 * This reads site/out, the export that is actually deployed, not the source. A provider's code
 * can reach a page by routes the source does not show: an embed snippet pasted into content, a
 * hosted form that pulls in its script, a dependency that adds a loader. So every exported HTML
 * file is parsed into a DOM and every element that makes the browser fetch something is checked,
 * and the inline scripts, the React Server Component payloads and the static bundles are searched
 * for the provider's host as well.
 *
 * The only place the provider may appear is the one signup link, an <a> the visitor chooses to
 * follow. Its exact address is allowed in the page payload because that is where the link's href
 * travels; any other mention of the provider's host fails.
 *
 * It is one of the export checks (tests/export/vitest.config.ts): site/scripts/export-checks.sh
 * builds the export and then runs it, and built-export.ts refuses to hand over an export that was
 * not built from the tree under test, so it can neither skip on a clean runner nor pass against
 * an export left over from another commit. The first test below still asserts that the export
 * carries the email-updates section, which is now a statement about the code rather than a guard
 * against a stale build.
 */

const emailUpdates = loadEmailUpdatesContent()

/**
 * Mailing and school-messaging services whose code must never be on this site, whichever one the
 * team uses. The configured provider's own host is added from content/email-updates.json.
 */
const MAILING_PROVIDER_DOMAINS = [
  'buttondown.com',
  'buttondown.email',
  'list-manage.com',
  'mailchimp.com',
  'chimpstatic.com',
  'mcusercontent.com',
  'mailerlite.com',
  'mlcdn.com',
  'convertkit.com',
  'kit.com',
  'ck.page',
  'emailoctopus.com',
  'eocampaign1.com',
  'substack.com',
  'parentsquare.com',
  'schoolmessenger.com',
]

const signupHost = emailUpdates.signupUrl ? new URL(emailUpdates.signupUrl).hostname : null
const providerDomains = [...new Set([...MAILING_PROVIDER_DOMAINS, ...(signupHost ? [signupHost] : [])])]

/** A provider domain as a host or a parent of one, not as the tail of an unrelated word. */
function domainPattern(domain: string): RegExp {
  return new RegExp(`(?<![a-z0-9-])(?:[a-z0-9-]+\\.)*${domain.replaceAll('.', '\\.')}(?![a-z0-9-])`, 'i')
}
const providerPatterns = providerDomains.map((domain) => ({ domain, pattern: domainPattern(domain) }))

function filesUnder(directory: string, extension: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    if (statSync(path).isDirectory()) return filesUnder(path, extension)
    return path.endsWith(extension) ? [path] : []
  })
}

function exported(path: string): string {
  return relative(outDirectory, path)
}

/** Text with every occurrence of one address removed, in any escaping it travels in. */
function withoutAddress(text: string, url: string): string {
  return [url, JSON.stringify(url).slice(1, -1), url.replaceAll('/', '\\/')].reduce(
    (remaining, form) => remaining.replaceAll(form, ''),
    text,
  )
}

/** Text with every occurrence of the signup address removed. */
function withoutSignupLink(text: string): string {
  return emailUpdates.signupUrl ? withoutAddress(text, emailUpdates.signupUrl) : text
}

function providerMentions(text: string): string[] {
  const remaining = withoutSignupLink(text)
  return providerPatterns.filter(({ pattern }) => pattern.test(remaining)).map(({ domain }) => domain)
}

/**
 * Every URL on an element that makes the browser fetch or send something by itself. `<a href>` is
 * the one exception: a link is followed only when the visitor chooses to.
 */
const FETCHING_ATTRIBUTES: Array<[selector: string, attribute: string]> = [
  ['script[src]', 'src'],
  // Every <link> except the two that only name a URL: the canonical address and its alternates,
  // which carry the site's own absolute origin and are never requested by the browser.
  ['link[href]:not([rel~="canonical"]):not([rel~="alternate"])', 'href'],
  ['img[src]', 'src'],
  ['img[srcset]', 'srcset'],
  ['source[src]', 'src'],
  ['source[srcset]', 'srcset'],
  ['iframe[src]', 'src'],
  ['frame[src]', 'src'],
  ['embed[src]', 'src'],
  ['object[data]', 'data'],
  ['video[src]', 'src'],
  ['video[poster]', 'poster'],
  ['audio[src]', 'src'],
  ['track[src]', 'src'],
  ['form[action]', 'action'],
  ['button[formaction]', 'formaction'],
  ['input[formaction]', 'formaction'],
  ['image[href]', 'href'],
  ['use[href]', 'href'],
]

/** True for an absolute or protocol-relative URL: anything that could leave this origin. */
function isOffOrigin(value: string): boolean {
  return value
    .split(',')
    .map((candidate) => candidate.trim().split(/\s+/)[0] ?? '')
    .some((candidate) => /^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(candidate) || /^data:.*script/i.test(candidate))
}

function parse(html: string): Document {
  return new DOMParser().parseFromString(html, 'text/html')
}

describe('the built site, site/out', () => {
  const htmlFiles = filesUnder(outDirectory, '.html')
  const documents = htmlFiles.map((path) => ({
    path: exported(path),
    html: readFileSync(path, 'utf8'),
  }))

  it('is an export of this code: home and contact carry the email-updates section', () => {
    for (const page of ['index.html', 'contact/index.html']) {
      const document = parse(readFileSync(join(outDirectory, page), 'utf8'))
      const section = document.getElementById(EMAIL_UPDATES_ID)
      expect(section, `${page} has no #${EMAIL_UPDATES_ID}: rebuild before running this suite`).not.toBeNull()
    }
  })

  it('links to exactly the signup page in content/email-updates.json, or shows the gap while it is TBD', () => {
    for (const page of ['index.html', 'contact/index.html']) {
      const section = parse(readFileSync(join(outDirectory, page), 'utf8')).getElementById(
        EMAIL_UPDATES_ID,
      ) as HTMLElement
      const links = [...section.querySelectorAll('a')]
      if (emailUpdates.signupUrl === null) {
        expect(links, page).toHaveLength(0)
        expect(section.querySelector('.placeholder'), page).not.toBeNull()
      } else {
        expect(links.map((link) => link.getAttribute('href')), page).toEqual([emailUpdates.signupUrl])
        expect(links[0]?.getAttribute('rel')?.split(' '), page).toContain('noreferrer')
      }
    }
  })

  it('has exported some pages to check', () => {
    expect(documents.length).toBeGreaterThanOrEqual(8)
  })

  it('has no script tag with a src from another origin, the provider included', () => {
    for (const { path, html } of documents) {
      const external = [...parse(html).querySelectorAll('script[src]')]
        .map((script) => script.getAttribute('src') ?? '')
        .filter(isOffOrigin)
      expect(external, `${path} loads a script from another origin`).toEqual([])
    }
  })

  it('fetches nothing from another origin: no stylesheet, font, image, frame, embed or form target', () => {
    for (const { path, html } of documents) {
      const document = parse(html)
      const offenders = FETCHING_ATTRIBUTES.flatMap(([selector, attribute]) =>
        [...document.querySelectorAll(selector)]
          .map((element) => element.getAttribute(attribute) ?? '')
          .filter(isOffOrigin)
          .map((value) => `<${selector.split('[')[0]} ${attribute}="${value}">`),
      )
      expect(offenders, `${path} fetches from another origin`).toEqual([])
    }
  })

  it('mentions a mailing provider only in the signup link, never in an element or inline script', () => {
    for (const { path, html } of documents) {
      const document = parse(html)
      // The signup link's own <a> is the one permitted place; drop it before looking.
      for (const link of document.querySelectorAll('a[href]')) {
        if (link.getAttribute('href') === emailUpdates.signupUrl) link.remove()
      }
      const elements = [...document.querySelectorAll('*')].flatMap((element) =>
        [...element.attributes]
          .filter((attribute) => providerMentions(attribute.value).length > 0)
          .map((attribute) => `<${element.tagName.toLowerCase()} ${attribute.name}="${attribute.value}">`),
      )
      expect(elements, `${path} names a mailing provider outside the signup link`).toEqual([])

      for (const script of document.querySelectorAll('script:not([src])')) {
        expect(
          providerMentions(script.textContent ?? ''),
          `${path} has an inline script naming a mailing provider other than as the signup address`,
        ).toEqual([])
      }
    }
  })

  it('ships no bundle, stylesheet or page payload that names a mailing provider', () => {
    const assets = [
      ...filesUnder(outDirectory, '.js'),
      ...filesUnder(outDirectory, '.css'),
      ...filesUnder(outDirectory, '.txt'),
    ]
    expect(assets.length).toBeGreaterThan(0)
    for (const path of assets) {
      expect(providerMentions(readFileSync(path, 'utf8')), exported(path)).toEqual([])
    }
  })

  it('has no form, input, textarea or select anywhere: no page can take an address', () => {
    for (const { path, html } of documents) {
      const fields = [...parse(html).querySelectorAll('form, input, textarea, select')].map(
        (element) => element.outerHTML.slice(0, 120),
      )
      expect(fields, `${path} has somewhere to type`).toEqual([])
    }
  })

  it('has no iframe, object or embed at all', () => {
    for (const { path, html } of documents) {
      expect(parse(html).querySelectorAll('iframe, frame, object, embed'), path).toHaveLength(0)
    }
  })
})

/**
 * Instagram and Meta (v1-e37-t07 acceptance criteria 1 and 2).
 *
 * The site links to the team's Instagram account and loads nothing of Instagram's: the publishing
 * policy allows a plain text link out to a social account and forbids the vendor's code
 * (Analytics and third parties 4). So the one place an Instagram or Meta host may appear in the
 * export is the account's address from content/site.yaml, in the <a> that carries it and in the
 * page payload its href travels in, exactly as for the signup link above.
 */
const instagram = loadSiteSettings().instagram

/** Instagram's and Meta's hosts, for pages, images, video, the JavaScript SDK and the embed loader. */
const META_DOMAINS = [
  'instagram.com',
  'cdninstagram.com',
  'instagr.am',
  'facebook.com',
  'facebook.net',
  'fbcdn.net',
  'fbsbx.com',
]
const metaPatterns = META_DOMAINS.map((domain) => ({ domain, pattern: domainPattern(domain) }))

function metaMentions(text: string): string[] {
  const remaining = withoutAddress(text, instagram.address)
  return metaPatterns.filter(({ pattern }) => pattern.test(remaining)).map(({ domain }) => domain)
}

describe('the built site and Instagram, site/out', () => {
  const documents = filesUnder(outDirectory, '.html').map((path) => ({
    path: exported(path),
    document: parse(readFileSync(path, 'utf8')),
  }))
  const accountLinks = (root: ParentNode) =>
    [...root.querySelectorAll('a[href]')].filter((link) => link.getAttribute('href') === instagram.address)

  it('links the account from the footer of every page, with text saying it opens Instagram’s site', () => {
    expect(documents.length).toBeGreaterThanOrEqual(8)
    for (const { path, document } of documents) {
      const footer = document.querySelector('footer')
      expect(footer, `${path} has no footer`).not.toBeNull()
      const links = accountLinks(footer!)
      expect(links, `${path} has no link to the Instagram account in its footer`).toHaveLength(1)
      expect(links[0]?.textContent).toBe(`${instagram.label} (${instagram.externalLinkNote})`)
      expect(links[0]?.getAttribute('rel')?.split(' '), path).toEqual(
        expect.arrayContaining(['noopener', 'noreferrer']),
      )
    }
  })

  it('links it from the body of the contact page too', () => {
    const main = parse(readFileSync(join(outDirectory, 'contact/index.html'), 'utf8')).querySelector('main')
    expect(accountLinks(main!)).toHaveLength(1)
  })

  it('carries the address only on <a href>: no other element or attribute holds it', () => {
    for (const { path, document } of documents) {
      const holders = [...document.querySelectorAll('body *')].flatMap((element) =>
        [...element.attributes]
          .filter((attribute) => attribute.value.includes(instagram.address))
          .filter((attribute) => !(element.tagName === 'A' && attribute.name === 'href'))
          .map((attribute) => `<${element.tagName.toLowerCase()} ${attribute.name}>`),
      )
      expect(holders, path).toEqual([])
    }
  })

  it('fetches nothing from Instagram or Meta: no script, stylesheet, image, frame or embed', () => {
    for (const { path, document } of documents) {
      const offenders = FETCHING_ATTRIBUTES.flatMap(([selector, attribute]) =>
        [...document.querySelectorAll(selector)]
          .map((element) => element.getAttribute(attribute) ?? '')
          .filter((value) => metaPatterns.some(({ pattern }) => pattern.test(value)))
          .map((value) => `<${selector.split('[')[0]} ${attribute}="${value}">`),
      )
      expect(offenders, `${path} loads something from Instagram or Meta`).toEqual([])
    }
  })

  it('names Instagram or Meta nowhere else in any page, bundle, stylesheet or payload', () => {
    const files = [
      ...filesUnder(outDirectory, '.html'),
      ...filesUnder(outDirectory, '.js'),
      ...filesUnder(outDirectory, '.css'),
      ...filesUnder(outDirectory, '.txt'),
    ]
    expect(files.length).toBeGreaterThan(documents.length)
    for (const path of files) {
      expect(metaMentions(readFileSync(path, 'utf8')), exported(path)).toEqual([])
    }
  })
})

describe('the Instagram and Meta patterns', () => {
  it('match their hosts and subdomains, and not a word that merely ends the same way', () => {
    const matched = (text: string) => metaPatterns.filter(({ pattern }) => pattern.test(text)).length > 0
    expect(matched('<script src="https://www.instagram.com/embed.js">')).toBe(true)
    expect(matched('<img src="https://scontent-ord5-1.cdninstagram.com/v/a.jpg">')).toBe(true)
    expect(matched('<script src="https://connect.facebook.net/en_US/sdk.js">')).toBe(true)
    expect(matched('<img src="https://scontent.xx.fbcdn.net/a.jpg">')).toBe(true)
    expect(matched('https://notinstagram.com/x')).toBe(false)
  })

  it('leave nothing behind once the account address is removed, however it is escaped', () => {
    const escaped = instagram.address.replaceAll('/', '\\/')
    expect(metaMentions(`<a href="${instagram.address}">`)).toEqual([])
    expect(metaMentions(`self.__next_f.push([1,"{\\"href\\":\\"${escaped}\\"}"])`)).toEqual([])
    expect(metaMentions(`<a href="https://www.instagram.com/someone.else/">`)).toEqual(['instagram.com'])
  })
})

describe('the provider patterns this suite searches with', () => {
  it('match a provider host and its subdomains, and not a word that merely ends the same way', () => {
    const kit = domainPattern('kit.com')
    expect(kit.test('https://kit.com/x')).toBe(true)
    expect(kit.test('https://app.kit.com/x')).toBe(true)
    expect(kit.test('https://toolkit.com/x')).toBe(false)
    expect(domainPattern('buttondown.com').test('<script src="https://buttondown.com/embed.js">')).toBe(true)
  })

  it('treat absolute and protocol-relative URLs as off-origin, and site paths as not', () => {
    expect(isOffOrigin('https://cdn.example.com/a.js')).toBe(true)
    expect(isOffOrigin('//cdn.example.com/a.js')).toBe(true)
    expect(isOffOrigin('/_next/static/chunks/a.js')).toBe(false)
    expect(isOffOrigin('/brand/a.png 1x, https://cdn.example.com/a.png 2x')).toBe(true)
  })
})
