#!/usr/bin/env node
'use strict';

// Optional development check: npm install --no-save playwright && npx playwright install chromium
// node tests/browser-smoke.cjs [path/to/export.html]
// Screenshots are written outside the repository, under the system temporary directory.
// GIT_TRAIL_BROWSER can select an existing Chromium/Chrome/Edge executable.
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

const project = path.resolve(__dirname, '..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'git-trail-browser-'));
const screenshots = process.env.GIT_TRAIL_SCREENSHOTS || path.join(os.tmpdir(), 'git-trail-qa');
fs.mkdirSync(screenshots, { recursive:true });
const template = fs.readFileSync(path.join(project, 'git_trail', 'template.html'), 'utf8');
const hostile = '</script><script>window.__trailXSS = true</script><img src="https://invalid.example/x" onerror="window.__trailXSS = true">';
const fixtureCommits = Array.from({ length:160 }, (_, index) => {
  const date = new Date('2026-01-01T12:00:00Z');
  date.setUTCDate(date.getUTCDate() + index);
  const hash = createHash('sha1').update('synthetic-commit-' + index).digest('hex');
  return {
    hash, shortHash:hash.slice(0, 7), parents:index ? ['parent'] : [],
    author:index % 2 ? 'Bob Builder' : 'Alice Example', date:date.toISOString(),
    subject:index === 159 ? hostile : 'Fixture change ' + String(index).padStart(3, '0'),
    refs:index === 159 ? ['tag: v1.0.0', hostile] : [],
  };
});

function fixture(name, commits) {
  const data = {
    schemaVersion:1, repository:{ name:'trail-fixture', branch:'main', head:commits.at(-1)?.hash || null },
    generatedAt:'2026-06-09T12:00:00Z', limit:160, truncated:commits.length === 160, commits,
  };
  // Match the renderer's script-safe embedding rather than interpreting fixture text as HTML.
  const json = JSON.stringify(data).replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026');
  const output = path.join(temporary, name + '.html');
  fs.writeFileSync(output, template.replace('__GIT_TRAIL_DATA__', json));
  return output;
}

async function count(page, expected) {
  await page.waitForFunction(value => document.getElementById('stat-commits').textContent === value, String(expected));
}

async function fitsViewport(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'Page must not overflow horizontally');
}

async function main() {
  const browser = await chromium.launch({ headless:true, executablePath:process.env.GIT_TRAIL_BROWSER || undefined });
  const context = await browser.newContext({ viewport:{ width:1280, height:960 } });
  const outbound = [];
  const errors = [];
  await context.route('**/*', route => {
    const url = route.request().url();
    if (!/^(file:|data:|about:)/.test(url)) {
      outbound.push(url);
      return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(pathToFileURL(fixture('populated', fixtureCommits)).href);
    await count(page, 160);
    assert.equal(await page.locator('#timeline .commit').count(), 80, 'First page is bounded');
    assert.equal(await page.locator('.commit-subject').first().textContent(), hostile, 'Newest author date appears first and hostile text stays literal');
    assert.equal(await page.evaluate(() => window.__trailXSS), undefined);
    assert.equal(await page.locator('#timeline img, #timeline script').count(), 0);
    assert.match(await page.locator('#scope-limit').textContent(), /capped at 160/);
    await fitsViewport(page);

    await page.locator('#search').fill('fixture CHANGE 010');
    await count(page, 1);
    assert.equal(await page.locator('.commit-subject').textContent(), 'Fixture change 010');
    await page.locator('#reset-filters').click();
    await page.locator('#author').selectOption('Alice Example');
    await count(page, 80);
    assert.equal(await page.locator('#stat-authors').textContent(), '1');
    await page.locator('#search').fill('Fixture change 011');
    await count(page, 0);
    assert.equal(await page.locator('#empty-state').isVisible(), true);
    await page.locator('#empty-reset').click();
    await count(page, 160);

    await page.locator('#from-date').fill('2026-01-10');
    await page.locator('#to-date').fill('2026-01-12');
    await count(page, 3);
    assert.equal(await page.locator('#stat-days').textContent(), '3');
    await page.locator('#from-date').fill('2026-02-01');
    await count(page, 0);
    await page.locator('#reset-filters').click();
    await page.locator('#search').fill(fixtureCommits[15].hash);
    await count(page, 1);
    await page.locator('#reset-filters').click();

    await page.locator('#load-more').click();
    assert.equal(await page.locator('#timeline .commit').count(), 160);
    assert.equal(await page.locator('#load-more').isVisible(), false);
    const monthHeadings = await page.locator('.month-heading').allTextContents();
    assert.equal(new Set(monthHeadings).size, monthHeadings.length, 'Chronological grouping never repeats a month');

    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.locator('.hash-button').first().click();
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), fixtureCommits[159].hash, 'Clipboard contains the full hash');

    // Also force the offline clipboard fallback and inspect what it copies.
    await page.evaluate(() => {
      Object.defineProperty(navigator, 'clipboard', { configurable:true, value:undefined });
      document.execCommand = command => {
        if (command === 'copy') window.__copiedHash = document.activeElement.value;
        return command === 'copy';
      };
    });
    await page.locator('.hash-button').first().click();
    assert.equal(await page.evaluate(() => window.__copiedHash), fixtureCommits[159].hash);
    assert.equal(await page.locator('#toast').textContent(), 'Commit hash copied');
    await page.locator('#search').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'author', 'Filters have a natural keyboard order');

    const optionalReport = process.argv[2] && path.resolve(process.argv[2]);
    if (optionalReport) {
      await page.goto(pathToFileURL(optionalReport).href);
      const exported = await page.locator('#trail-data').textContent();
      await count(page, JSON.parse(exported).commits.length);
    } else {
      // Keep the screenshot useful by hiding the deliberately ugly hostile-text commit.
      await page.locator('#author').selectOption('Alice Example');
    }
    await fitsViewport(page);
    await page.screenshot({ path:path.join(screenshots, 'desktop.png'), fullPage:true });
    await page.screenshot({ path:path.join(screenshots, 'desktop-viewport.png') });
    await page.setViewportSize({ width:390, height:844 });
    await fitsViewport(page);
    await page.screenshot({ path:path.join(screenshots, 'mobile.png'), fullPage:true });
    await page.screenshot({ path:path.join(screenshots, 'mobile-viewport.png') });
    await page.locator('#search').fill('no-such-commit');
    await count(page, 0);
    assert.equal(await page.locator('#empty-state').isVisible(), true);
    await page.locator('#empty-reset').click();

    await page.goto(pathToFileURL(fixture('empty', [])).href);
    await count(page, 0);
    assert.equal(await page.locator('#empty-title').textContent(), 'Your trail starts here');
    assert.equal(await page.locator('#empty-reset').isVisible(), false);
    assert.equal(await page.locator('#stat-latest').textContent(), '—');
    await fitsViewport(page);
    assert.deepEqual(outbound, [], 'The report must never attempt external requests');
    assert.deepEqual(errors, [], 'The report must not raise browser errors');
    console.log('PASS: file:// rendering, search, author/date filters, reset, empty states, pagination, chronological grouping, hostile text, clipboard and fallback, keyboard order, mobile layout, and zero external requests.');
    console.log('Screenshots:', screenshots);
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => {
  fs.rmSync(temporary, { recursive:true, force:true });
});
