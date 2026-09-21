import nextCoreWebVitals from 'eslint-config-next/core-web-vitals'
import nextTypeScript from 'eslint-config-next/typescript'
import jsxA11y from 'eslint-plugin-jsx-a11y'

/**
 * `next/core-web-vitals` registers the jsx-a11y plugin but turns on only a subset of its rules.
 * The site commits to a WCAG 2.1 AA floor, so the plugin's full recommended rule set is layered
 * on top: an accessibility mistake fails lint rather than waiting for the axe-core assertions in
 * vitest, which only cover the components a test happens to render.
 *
 * Only the rules are spread, not the plugin registration: a flat config may not define the same
 * plugin name twice, and Next has already defined it.
 */
const siteEslintConfig = [
  { ignores: ['.next/**', 'out/**', 'node_modules/**', 'next-env.d.ts'] },
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    name: 'site/jsx-a11y-recommended',
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      // The HTML that reaches <Prose> is rendered from Markdown committed in this repository, by
      // src/lib/content.ts, at build time. Nothing user-supplied can reach it.
      'react/no-danger': 'off',
      '@typescript-eslint/consistent-type-imports': 'error',
    },
  },
]

export default siteEslintConfig
