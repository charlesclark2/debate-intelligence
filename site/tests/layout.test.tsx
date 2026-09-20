import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { Button } from '@/components/Button'
import { Card } from '@/components/Card'
import { CardGrid } from '@/components/CardGrid'
import { MAIN_CONTENT_ID } from '@/components/landmark-ids'
import { Prose } from '@/components/Prose'
import { Section } from '@/components/Section'
import { SiteFrame } from '@/components/SiteFrame'

import { describeViolations, findAccessibilityViolations } from './axe'

const strings = {
  shortName: 'WFB Debate',
  skipLinkLabel: 'Skip to main content',
  navigationLabel: 'Main',
  logoAlternativeText: 'Whitefish Bay Blue Dukes',
  footerNote: 'Whitefish Bay High School, Whitefish Bay, Wisconsin.',
}

const items = [
  { href: '/', label: 'Home' },
  { href: '/accessibility/', label: 'Accessibility' },
]

/**
 * Landmark rules only hold when the regions are top level, so the frame is rendered straight
 * into document.body rather than into the wrapper div testing-library adds by default.
 */
function renderFrame() {
  return render(
    <SiteFrame items={items} strings={strings}>
      <h1>Placeholder heading</h1>
      <p>Placeholder body copy.</p>
    </SiteFrame>,
    { container: document.body },
  )
}

/**
 * next/link settles its own internal state a microtask after mount. Flushing it keeps React's
 * "not wrapped in act" warning out of the test output, so a real warning from our own
 * components would stand out.
 */
async function flushPendingEffects() {
  await act(async () => {})
}

describe('the page frame', () => {
  it('puts a skip link first, pointing at the main landmark', () => {
    renderFrame()
    const skipLink = screen.getByRole('link', { name: strings.skipLinkLabel })
    expect(skipLink).toHaveProperty('href', expect.stringContaining(`#${MAIN_CONTENT_ID}`))
    expect(document.body.firstElementChild).toBe(skipLink)
  })

  it('exposes banner, navigation, main and contentinfo landmarks', () => {
    renderFrame()
    expect(screen.getByRole('banner')).toBeDefined()
    expect(screen.getByRole('navigation', { name: strings.navigationLabel })).toBeDefined()
    expect(screen.getByRole('contentinfo')).toBeDefined()

    const main = screen.getByRole('main')
    expect(main.id).toBe(MAIN_CONTENT_ID)
    // The skip link can only move focus into <main> if it is programmatically focusable.
    expect(main.getAttribute('tabindex')).toBe('-1')
  })

  it('gives the logo a text alternative and links it home', () => {
    renderFrame()
    const logo = screen.getByAltText(strings.logoAlternativeText)
    expect(logo.closest('a')?.getAttribute('href')).toBe('/')
  })

  it('uses the wordmark as text in the footer, not the white-background mark', () => {
    renderFrame()
    const footer = screen.getByRole('contentinfo')
    expect(within(footer).getByText(strings.shortName)).toBeDefined()
    expect(within(footer).queryByRole('img')).toBeNull()
  })

  it('has no WCAG 2.1 AA violations', async () => {
    renderFrame()
    await flushPendingEffects()
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toHaveLength(0)
  })
})

describe('the mobile navigation menu', () => {
  it('starts collapsed and is announced as a disclosure', () => {
    renderFrame()
    const toggle = screen.getByRole('button', { name: /menu/i })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(toggle.getAttribute('aria-controls')).toBe(
      screen.getByRole('navigation', { name: strings.navigationLabel }).querySelector('ul')?.id,
    )
  })

  it('opens and closes from the keyboard alone', async () => {
    const user = userEvent.setup()
    renderFrame()
    const toggle = screen.getByRole('button', { name: /menu/i })

    toggle.focus()
    await user.keyboard('{Enter}')
    expect(toggle.getAttribute('aria-expanded')).toBe('true')

    await user.keyboard(' ')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
  })

  it('closes on Escape and returns focus to the toggle', async () => {
    const user = userEvent.setup()
    renderFrame()
    const toggle = screen.getByRole('button', { name: /menu/i })

    toggle.focus()
    await user.keyboard('{Enter}')
    expect(toggle.getAttribute('aria-expanded')).toBe('true')

    await user.keyboard('{Escape}')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(toggle)
  })

  it('reaches every navigation link by tabbing', async () => {
    const user = userEvent.setup()
    renderFrame()
    const toggle = screen.getByRole('button', { name: /menu/i })
    toggle.focus()
    await user.keyboard('{Enter}')

    // Asserted by link text: next/link normalises the trailing slash outside a Next build,
    // where the trailingSlash setting in next.config.ts is not in play.
    for (const item of items) {
      await user.tab()
      expect(document.activeElement?.tagName).toBe('A')
      expect(document.activeElement?.textContent).toBe(item.label)
    }
  })

  it('has no WCAG 2.1 AA violations while open', async () => {
    const user = userEvent.setup()
    renderFrame()
    await user.click(screen.getByRole('button', { name: /menu/i }))
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toHaveLength(0)
  })
})

describe('the shared components', () => {
  it('renders a link-style button and a real button, both with accessible names', async () => {
    const { container } = render(
      <div>
        <Button href="/accessibility/">Read the accessibility statement</Button>
        <Button variant="secondary">Show more</Button>
      </div>,
    )
    await flushPendingEffects()
    expect(screen.getByRole('link', { name: 'Read the accessibility statement' })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Show more' })).toBeDefined()

    const violations = await findAccessibilityViolations(container)
    expect(violations, describeViolations(violations)).toHaveLength(0)
  })

  it('lets a card choose its heading level so the outline stays unbroken', async () => {
    const { container } = render(
      <main>
        <h1>Page heading</h1>
        <Card title="A section">
          <p>Body copy.</p>
        </Card>
        <Card headingLevel={3} title="A sub-section">
          <p>Body copy.</p>
        </Card>
      </main>,
    )
    expect(screen.getByRole('heading', { level: 2, name: 'A section' })).toBeDefined()
    expect(screen.getByRole('heading', { level: 3, name: 'A sub-section' })).toBeDefined()

    const violations = await findAccessibilityViolations(container)
    expect(violations, describeViolations(violations)).toHaveLength(0)
  })

  it('renders build-time Markdown HTML without violations', async () => {
    const { container } = render(
      <main>
        <h1>Page heading</h1>
        <Prose html="<h2>A heading</h2><p>Some copy with a <a href=&quot;/&quot;>link</a>.</p>" />
      </main>,
    )
    expect(screen.getByRole('heading', { level: 2, name: 'A heading' })).toBeDefined()

    const violations = await findAccessibilityViolations(container)
    expect(violations, describeViolations(violations)).toHaveLength(0)
  })
})

/**
 * The layout kit added by v1-e36-t06. These assertions render it through the real SiteFrame, so
 * the landmark structure the rest of this file pins down is the structure the kit lands in: a
 * band is a <section> inside <main>, never a second <main> or a bare <div> that has lost its
 * place in the outline.
 */
describe('the layout kit', () => {
  const bands = (
    <>
      <Section eyebrow="Start here" id="entry" title="Four things worth knowing" tone="tinted">
        <CardGrid columns={2}>
          <Card headingLevel={3} title="What the events are">
            <p>Body copy.</p>
          </Card>
          <Card headingLevel={3} title="How to join">
            <p>Body copy.</p>
          </Card>
        </CardGrid>
      </Section>
      <Section id="session" title="Parent information session" tone="inverse">
        <p>Body copy.</p>
      </Section>
    </>
  )

  function renderBands() {
    return render(
      <SiteFrame items={items} strings={strings}>
        <h1>Page heading</h1>
        {bands}
      </SiteFrame>,
      { container: document.body },
    )
  }

  it('puts every band inside the main landmark', () => {
    const { container } = renderBands()
    const sections = container.querySelectorAll('main > section')
    expect(sections).toHaveLength(2)
    expect(container.querySelectorAll('main')).toHaveLength(1)
  })

  it('names a titled band for a screen reader and leaves the outline unbroken', () => {
    renderBands()
    const band = document.getElementById('entry')
    expect(band?.getAttribute('aria-labelledby')).toBe('entry-title')
    expect(screen.getByRole('heading', { level: 2, name: 'Four things worth knowing' })).toBeDefined()
    expect(screen.getByRole('heading', { level: 3, name: 'How to join' })).toBeDefined()
  })

  it('carries the tone on the element, so the surface is one class not a set of overrides', () => {
    renderBands()
    expect(document.getElementById('entry')?.className).toContain('section--tinted')
    expect(document.getElementById('session')?.className).toContain('section--inverse')
  })

  it('lays the cards out as a list, one item per card', () => {
    const { container } = renderBands()
    const grid = container.querySelector('.card-grid')
    expect(grid?.tagName).toBe('UL')
    expect(grid?.className).toContain('card-grid--2-up')
    expect(grid?.querySelectorAll(':scope > li.card-grid__item')).toHaveLength(2)
    // A <ul> may contain only <li>, so each Card's <article> has to be wrapped rather than
    // dropped straight into the grid.
    for (const item of grid?.querySelectorAll(':scope > li') ?? []) {
      expect(item.firstElementChild?.tagName).toBe('ARTICLE')
    }
  })

  it('renders a band with no heading at all, for a hero', () => {
    const { container } = render(
      <main>
        <Section>
          <p>Body copy with no section heading above it.</p>
        </Section>
      </main>,
    )
    const band = container.querySelector('section')
    expect(band?.getAttribute('aria-labelledby')).toBeNull()
    expect(band?.querySelector('.section__header')).toBeNull()
  })

  it('has no WCAG 2.1 AA violations', async () => {
    renderBands()
    await flushPendingEffects()
    const violations = await findAccessibilityViolations(document.body)
    expect(violations, describeViolations(violations)).toHaveLength(0)
  })
})
