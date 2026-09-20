import axe from 'axe-core'

/**
 * Runs axe-core over a container and returns the WCAG 2.1 level A and AA violations.
 *
 * jsdom has no layout engine, so axe cannot evaluate the colour-contrast rule here; it is
 * disabled explicitly rather than left to fail silently, and contrast is asserted against the
 * design tokens in tests/tokens.test.ts instead.
 */
export async function findAccessibilityViolations(
  container: Element,
): Promise<axe.Result[]> {
  const results = await axe.run(container, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
    rules: { 'color-contrast': { enabled: false } },
  })
  return results.violations
}

export function describeViolations(violations: axe.Result[]): string {
  return violations
    .map(
      (violation) =>
        `${violation.id} (${violation.impact ?? 'unknown'}): ${violation.help}\n  ` +
        violation.nodes.map((node) => node.target.join(' ')).join('\n  '),
    )
    .join('\n')
}
