/**
 * Tests for textPath references and element preservation
 *
 * Tests that:
 * - Elements referenced by textPath are preserved
 * - Elements referenced by use are preserved
 * - Elements referenced by url(#...) in styles are preserved
 */

import { describe, it, expect, afterAll } from 'vitest';
import {
  createPageWithSvg,
  getBBoxById,
  closeBrowser,
  assertValidBBox
} from '../helpers/browser-test.js';

describe('textPath and reference handling', () => {
  afterAll(async () => {
    await closeBrowser();
  });

  it('should measure text with textPath reference', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
           width="500" height="300"
           viewBox="0 0 500 300">
        <path id="curved-path" d="M 50 150 Q 250 50 450 150" fill="none" stroke="none"/>
        <text id="curved-text" font-size="24" fill="blue">
          <textPath xlink:href="#curved-path" startOffset="50%">
            Hello World
          </textPath>
        </text>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    // Test that the text element can be measured (path should be preserved)
    const bbox = await getBBoxById(page, 'curved-text');
    assertValidBBox(bbox);

    // Should have reasonable dimensions for "Hello World" on a curve
    expect(bbox.width).toBeGreaterThan(50);
    expect(bbox.height).toBeGreaterThan(10);

    await page.close();
  });

  it('should measure path referenced by textPath', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
           width="500" height="300"
           viewBox="0 0 500 300">
        <path id="visible-path" d="M 50 150 Q 250 50 450 150"
              fill="none" stroke="red" stroke-width="3"/>
        <text font-size="24" fill="blue">
          <textPath xlink:href="#visible-path" startOffset="50%">
            Curved
          </textPath>
        </text>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    // Test that the path itself can be measured (has visible stroke)
    const bbox = await getBBoxById(page, 'visible-path');
    assertValidBBox(bbox);

    // Should span from x=50 to x=450
    expect(bbox.x).toBeGreaterThanOrEqual(45);
    expect(bbox.x).toBeLessThanOrEqual(55);
    expect(bbox.width).toBeGreaterThanOrEqual(390);
    expect(bbox.width).toBeLessThanOrEqual(410);

    await page.close();
  });

  it('should preserve gradient references', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="200" height="200"
           viewBox="0 0 200 200">
        <defs>
          <linearGradient id="my-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" style="stop-color:rgb(255,0,0);stop-opacity:1" />
            <stop offset="100%" style="stop-color:rgb(0,0,255);stop-opacity:1" />
          </linearGradient>
        </defs>
        <rect id="gradient-rect" x="50" y="50" width="100" height="100"
              style="fill:url(#my-gradient)"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'gradient-rect');
    assertValidBBox(bbox);

    expect(bbox.x).toBeCloseTo(50, 0);
    expect(bbox.y).toBeCloseTo(50, 0);
    expect(bbox.width).toBeCloseTo(100, 0);

    await page.close();
  });

  it('should preserve filter references', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="200" height="200"
           viewBox="0 0 200 200">
        <defs>
          <filter id="my-blur">
            <feGaussianBlur in="SourceGraphic" stdDeviation="2" />
          </filter>
        </defs>
        <rect id="filtered-rect" x="50" y="50" width="100" height="100"
              fill="green" style="filter:url(#my-blur)"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'filtered-rect');
    assertValidBBox(bbox);

    // Filter expands bbox slightly due to blur
    expect(bbox.x).toBeLessThanOrEqual(50);
    expect(bbox.width).toBeGreaterThanOrEqual(100);

    await page.close();
  });

  it('should handle use element references', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
           width="200" height="200"
           viewBox="0 0 200 200">
        <defs>
          <circle id="my-circle" cx="0" cy="0" r="20" fill="purple"/>
        </defs>
        <use id="circle-use" xlink:href="#my-circle" x="100" y="100"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'circle-use');
    assertValidBBox(bbox);

    // Circle at (100, 100) with radius 20
    expect(bbox.x).toBeCloseTo(80, 0);
    expect(bbox.y).toBeCloseTo(80, 0);
    expect(bbox.width).toBeCloseTo(40, 0);

    await page.close();
  });

  it('should handle nested textPath with transform', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
           width="500" height="500"
           viewBox="0 0 500 500">
        <g transform="translate(50, 50)">
          <path id="nested-path" d="M 0 100 Q 200 0 400 100" fill="none" stroke="none"/>
          <text id="nested-text" font-size="20" fill="black" transform="rotate(15)">
            <textPath xlink:href="#nested-path" startOffset="50%">
              Transform Test
            </textPath>
          </text>
        </g>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'nested-text');
    assertValidBBox(bbox);

    // Should have non-zero dimensions despite transforms
    expect(bbox.width).toBeGreaterThan(30);
    expect(bbox.height).toBeGreaterThan(10);

    await page.close();
  });
});
