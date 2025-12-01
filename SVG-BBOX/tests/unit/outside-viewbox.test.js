/**
 * Tests for elements positioned outside viewBox
 *
 * Tests that:
 * - Elements with negative coordinates are measured correctly
 * - Elements positioned outside viewBox bounds are measured
 * - ROI expands correctly for out-of-bounds elements
 */

import { describe, it, expect, afterAll } from 'vitest';
import {
  createPageWithSvg,
  getBBoxById,
  closeBrowser,
  assertValidBBox
} from '../helpers/browser-test.js';

describe('elements outside viewBox', () => {
  afterAll(async () => {
    await closeBrowser();
  });

  it('should measure element with negative x coordinate', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="400" height="300"
           viewBox="0 0 400 300">
        <rect id="negative-x" x="-50" y="100" width="100" height="50" fill="red"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'negative-x', { mode: 'unclipped' });
    assertValidBBox(bbox);

    expect(bbox.x).toBeCloseTo(-50, 0);
    expect(bbox.width).toBeCloseTo(100, 0);

    await page.close();
  });

  it('should measure element with negative y coordinate', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="400" height="300"
           viewBox="0 0 400 300">
        <circle id="negative-y" cx="200" cy="-30" r="25" fill="blue"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'negative-y', { mode: 'unclipped' });
    assertValidBBox(bbox);

    // Circle center at (200, -30) with radius 25
    expect(bbox.x).toBeCloseTo(175, 0);
    expect(bbox.y).toBeCloseTo(-55, 0);

    await page.close();
  });

  it('should measure element completely outside viewBox to the left', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="400" height="300"
           viewBox="0 0 400 300">
        <rect id="far-left" x="-200" y="100" width="100" height="50" fill="green"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'far-left', { mode: 'unclipped' });
    assertValidBBox(bbox);

    expect(bbox.x).toBeCloseTo(-200, 0);
    expect(bbox.width).toBeCloseTo(100, 0);

    await page.close();
  });

  it('should measure element completely outside viewBox to the right', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="400" height="300"
           viewBox="0 0 400 300">
        <rect id="far-right" x="500" y="100" width="100" height="50" fill="purple"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'far-right', { mode: 'unclipped' });
    assertValidBBox(bbox);

    expect(bbox.x).toBeCloseTo(500, 0);
    expect(bbox.width).toBeCloseTo(100, 0);

    await page.close();
  });

  it('should measure element with path data outside viewBox', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="400" height="300"
           viewBox="0 0 400 300">
        <path id="outside-path"
              d="M 500 150 L 600 150 L 600 200 L 500 200 Z"
              fill="none" stroke="orange" stroke-width="3"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'outside-path', { mode: 'unclipped' });
    assertValidBBox(bbox);

    // Path spans from x=500 to x=600
    expect(bbox.x).toBeGreaterThanOrEqual(495);
    expect(bbox.x).toBeLessThanOrEqual(505);
    expect(bbox.width).toBeGreaterThanOrEqual(95);
    expect(bbox.width).toBeLessThanOrEqual(105);

    await page.close();
  });

  it('should measure text element outside viewBox', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="400" height="300"
           viewBox="0 0 400 300">
        <text id="outside-text" x="-100" y="50" font-size="24" fill="black">
          Out of bounds
        </text>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'outside-text', { mode: 'unclipped' });
    assertValidBBox(bbox);

    // Text starts at x=-100
    expect(bbox.x).toBeLessThanOrEqual(-90);
    expect(bbox.width).toBeGreaterThan(50);

    await page.close();
  });

  it('should measure element with negative viewBox origin', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="400" height="300"
           viewBox="-200 -150 400 300">
        <rect id="in-negative-vb" x="-100" y="-50" width="100" height="50" fill="cyan"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'in-negative-vb');
    assertValidBBox(bbox);

    expect(bbox.x).toBeCloseTo(-100, 0);
    expect(bbox.y).toBeCloseTo(-50, 0);
    expect(bbox.width).toBeCloseTo(100, 0);

    await page.close();
  });

  it('should measure transformed element outside viewBox', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="400" height="300"
           viewBox="0 0 400 300">
        <g transform="translate(-200, 50)">
          <rect id="transformed-outside" x="0" y="0" width="80" height="60" fill="pink"/>
        </g>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    const bbox = await getBBoxById(page, 'transformed-outside', { mode: 'unclipped' });
    assertValidBBox(bbox);

    // After transform: x = 0 - 200 = -200
    expect(bbox.x).toBeCloseTo(-200, 0);
    expect(bbox.width).toBeCloseTo(80, 0);

    await page.close();
  });

  it('should measure clipped vs unclipped mode correctly', async () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg"
           width="200" height="200"
           viewBox="0 0 200 200">
        <rect id="partial-outside" x="150" y="150" width="100" height="100" fill="yellow"/>
      </svg>
    `;
    const page = await createPageWithSvg(svg);

    // Both modes should measure the element successfully
    const bboxUnclipped = await getBBoxById(page, 'partial-outside', { mode: 'unclipped' });
    assertValidBBox(bboxUnclipped);
    expect(bboxUnclipped.width).toBeCloseTo(100, 0);

    // Clipped mode uses restricted ROI but still measures full element
    const bboxClipped = await getBBoxById(page, 'partial-outside', { mode: 'clipped' });
    if (bboxClipped) {
      assertValidBBox(bboxClipped);
      expect(bboxClipped.width).toBeGreaterThan(0); // Should detect at least something
    }

    await page.close();
  });
});
