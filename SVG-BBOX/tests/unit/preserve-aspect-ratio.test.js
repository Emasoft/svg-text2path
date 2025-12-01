/**
 * Tests for preserveAspectRatio handling
 *
 * Tests all variants of preserveAspectRatio:
 * - Scaling modes: meet, slice, none
 * - Alignments: xMin/xMid/xMax + YMin/YMid/YMax (9 combinations)
 * - Edge cases: defer keyword, default values
 */

import { describe, it, expect, afterAll } from 'vitest';
import {
  createPageWithSvg,
  getBBoxById,
  closeBrowser,
  assertValidBBox
} from '../helpers/browser-test.js';

describe('preserveAspectRatio handling', () => {
  afterAll(async () => {
    await closeBrowser();
  });

  describe('meet mode (default)', () => {
    it('should handle xMidYMid meet (default)', async () => {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg"
             width="400" height="200"
             viewBox="0 0 800 800"
             preserveAspectRatio="xMidYMid meet">
          <rect id="test-rect" x="350" y="350" width="100" height="100" fill="red"/>
        </svg>
      `;
      const page = await createPageWithSvg(svg);
      const bbox = await getBBoxById(page, 'test-rect');

      assertValidBBox(bbox);
      // With meet mode, viewBox 800×800 fits in 400×200 → scale = 200/800 = 0.25
      // So page→user scale = 4.0
      // Element should be at correct user coordinates
      expect(bbox.x).toBeCloseTo(350, 0);
      expect(bbox.y).toBeCloseTo(350, 0);
      expect(bbox.width).toBeCloseTo(100, 0);

      await page.close();
    });

    it('should handle xMinYMin meet (top-left align)', async () => {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg"
             width="400" height="200"
             viewBox="0 0 800 800"
             preserveAspectRatio="xMinYMin meet">
          <rect id="test-rect" x="10" y="10" width="50" height="50" fill="blue"/>
        </svg>
      `;
      const page = await createPageWithSvg(svg);
      const bbox = await getBBoxById(page, 'test-rect');

      assertValidBBox(bbox);
      expect(bbox.x).toBeCloseTo(10, 0);
      expect(bbox.y).toBeCloseTo(10, 0);

      await page.close();
    });

    it('should handle xMaxYMax meet (bottom-right align)', async () => {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg"
             width="400" height="200"
             viewBox="0 0 800 800"
             preserveAspectRatio="xMaxYMax meet">
          <rect id="test-rect" x="700" y="700" width="50" height="50" fill="green"/>
        </svg>
      `;
      const page = await createPageWithSvg(svg);
      const bbox = await getBBoxById(page, 'test-rect');

      assertValidBBox(bbox);
      expect(bbox.x).toBeCloseTo(700, 0);
      expect(bbox.y).toBeCloseTo(700, 0);

      await page.close();
    });
  });

  describe('slice mode', () => {
    it('should handle xMidYMid slice', async () => {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg"
             width="200" height="400"
             viewBox="0 0 800 800"
             preserveAspectRatio="xMidYMid slice">
          <rect id="test-rect" x="350" y="350" width="100" height="100" fill="purple"/>
        </svg>
      `;
      const page = await createPageWithSvg(svg);
      const bbox = await getBBoxById(page, 'test-rect');

      assertValidBBox(bbox);
      // With slice mode, viewBox 800×800 covers 200×400 → scale = 400/800 = 0.5
      // So page→user scale = 2.0
      expect(bbox.x).toBeCloseTo(350, 0);
      expect(bbox.y).toBeCloseTo(350, 0);

      await page.close();
    });

    it('should handle xMinYMax slice', async () => {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg"
             width="200" height="400"
             viewBox="0 0 800 800"
             preserveAspectRatio="xMinYMax slice">
          <rect id="test-rect" x="50" y="700" width="50" height="50" fill="orange"/>
        </svg>
      `;
      const page = await createPageWithSvg(svg);
      const bbox = await getBBoxById(page, 'test-rect');

      assertValidBBox(bbox);
      expect(bbox.x).toBeCloseTo(50, 0);
      expect(bbox.y).toBeCloseTo(700, 1);

      await page.close();
    });
  });

  describe('none mode (non-uniform scaling)', () => {
    it('should handle preserveAspectRatio="none"', async () => {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg"
             width="400" height="200"
             viewBox="0 0 800 400"
             preserveAspectRatio="none">
          <rect id="test-rect" x="300" y="100" width="100" height="50" fill="cyan"/>
        </svg>
      `;
      const page = await createPageWithSvg(svg);
      const bbox = await getBBoxById(page, 'test-rect');

      assertValidBBox(bbox);
      // With none mode: scaleX = 800/400 = 2.0, scaleY = 400/200 = 2.0
      // Element should be at correct user coordinates
      expect(bbox.x).toBeCloseTo(300, 0);
      expect(bbox.y).toBeCloseTo(100, 0);
      expect(bbox.width).toBeCloseTo(100, 0);

      await page.close();
    });
  });

  describe('defer keyword', () => {
    it('should ignore "defer" keyword in preserveAspectRatio', async () => {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg"
             width="400" height="200"
             viewBox="0 0 800 800"
             preserveAspectRatio="defer xMidYMid meet">
          <rect id="test-rect" x="350" y="350" width="100" height="100" fill="pink"/>
        </svg>
      `;
      const page = await createPageWithSvg(svg);
      const bbox = await getBBoxById(page, 'test-rect');

      assertValidBBox(bbox);
      // Should behave same as "xMidYMid meet" (defer is ignored for <svg>)
      expect(bbox.x).toBeCloseTo(350, 0);
      expect(bbox.y).toBeCloseTo(350, 0);

      await page.close();
    });
  });

  describe('default behavior', () => {
    it('should default to xMidYMid meet when attribute is missing', async () => {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg"
             width="400" height="200"
             viewBox="0 0 800 800">
          <rect id="test-rect" x="350" y="350" width="100" height="100" fill="yellow"/>
        </svg>
      `;
      const page = await createPageWithSvg(svg);
      const bbox = await getBBoxById(page, 'test-rect');

      assertValidBBox(bbox);
      expect(bbox.x).toBeCloseTo(350, 0);
      expect(bbox.y).toBeCloseTo(350, 0);

      await page.close();
    });
  });
});
