/**
 * The day every test builds the site as of (v1-e37-t03). An announcement is published from its
 * date through its expiry, judged against the build date, so a test that read the clock would pass
 * or fail by the day it ran. tests/setup.ts sets SITE_BUILD_DATE to this before every test, and
 * the loader reads that before the clock; a test about another day stubs its own.
 */
export const TEST_BUILD_DATE = '2026-11-02'
