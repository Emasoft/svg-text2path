/**
 * Registry-based Installation Test
 *
 * This test verifies that the package works correctly when installed from
 * the npm registry (as opposed to the local tarball test in package-installation.test.js).
 *
 * IMPORTANT: This test only runs in post-publish verification scenarios.
 * It requires the VERIFY_NPM_VERSION environment variable to be set to the
 * version that was just published.
 *
 * Usage:
 *   VERIFY_NPM_VERSION=1.0.12 pnpm test -- tests/integration/registry-installation.test.js
 *
 * When to use:
 *   - After npm publish to verify the published package works
 *   - In CI after the publish workflow completes
 *   - As part of release.sh post-publish verification
 *
 * What it tests:
 *   - npm install svg-bbox@VERSION from registry works
 *   - All 13 CLI tools are executable via node_modules/.bin/
 *   - Library can be require()'d without errors
 *   - Version matches expected version
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import os from 'os';

// Skip entire test suite if VERIFY_NPM_VERSION is not set
const VERIFY_NPM_VERSION = process.env.VERIFY_NPM_VERSION;
const SKIP_REGISTRY_TEST = !VERIFY_NPM_VERSION;

// All CLI tools defined in package.json bin
const CLI_TOOLS = [
  'svg-bbox',
  'sbb-getbbox',
  'sbb-chrome-getbbox',
  'sbb-inkscape-getbbox',
  'sbb-extract',
  'sbb-chrome-extract',
  'sbb-inkscape-extract',
  'sbb-svg2png',
  'sbb-fix-viewbox',
  'sbb-comparer',
  'sbb-test',
  'sbb-inkscape-text2path',
  'sbb-inkscape-svg2png'
];

// Timeout for npm install (can be slow)
const NPM_INSTALL_TIMEOUT = 120000; // 2 minutes

describe.skipIf(SKIP_REGISTRY_TEST)('Registry Installation Verification', () => {
  let testDir;
  let binDir;

  beforeAll(() => {
    // Create a clean temp directory for installation
    testDir = fs.mkdtempSync(path.join(os.tmpdir(), 'svg-bbox-registry-test-'));
    binDir = path.join(testDir, 'node_modules', '.bin');

    console.log(`\n[Registry Test] Installing svg-bbox@${VERIFY_NPM_VERSION} from npm registry...`);
    console.log(`[Registry Test] Test directory: ${testDir}`);

    // Initialize a minimal package.json
    const packageJson = {
      name: 'svg-bbox-registry-test',
      version: '1.0.0',
      private: true
    };
    fs.writeFileSync(path.join(testDir, 'package.json'), JSON.stringify(packageJson, null, 2));

    // Install svg-bbox from npm registry using spawnSync (safe, no shell)
    const result = spawnSync('npm', ['install', `svg-bbox@${VERIFY_NPM_VERSION}`], {
      cwd: testDir,
      timeout: NPM_INSTALL_TIMEOUT,
      encoding: 'utf8',
      env: { ...process.env, npm_config_registry: 'https://registry.npmjs.org/' }
    });

    if (result.status !== 0) {
      console.error(`[Registry Test] Installation failed with code ${result.status}`);
      if (result.stdout) console.error('stdout:', result.stdout);
      if (result.stderr) console.error('stderr:', result.stderr);
      throw new Error(`Failed to install svg-bbox@${VERIFY_NPM_VERSION} from npm registry`);
    }

    console.log(`[Registry Test] Installation successful`);
  }, NPM_INSTALL_TIMEOUT + 10000);

  afterAll(() => {
    // Clean up temp directory
    if (testDir && fs.existsSync(testDir)) {
      try {
        fs.rmSync(testDir, { recursive: true, force: true });
        console.log(`[Registry Test] Cleaned up test directory`);
      } catch {
        console.warn(`[Registry Test] Warning: Could not clean up ${testDir}`);
      }
    }
  });

  describe('Package Structure', () => {
    it('should have node_modules/svg-bbox directory', () => {
      const pkgDir = path.join(testDir, 'node_modules', 'svg-bbox');
      expect(fs.existsSync(pkgDir)).toBe(true);
    });

    it('should have SvgVisualBBox.js library file', () => {
      const libPath = path.join(testDir, 'node_modules', 'svg-bbox', 'SvgVisualBBox.js');
      expect(fs.existsSync(libPath)).toBe(true);
    });

    it('should have SvgVisualBBox.min.js minified file', () => {
      const minPath = path.join(testDir, 'node_modules', 'svg-bbox', 'SvgVisualBBox.min.js');
      expect(fs.existsSync(minPath)).toBe(true);
    });

    it('should have lib/ directory with utilities', () => {
      const libDir = path.join(testDir, 'node_modules', 'svg-bbox', 'lib');
      expect(fs.existsSync(libDir)).toBe(true);
    });

    it('should have config/ directory', () => {
      const configDir = path.join(testDir, 'node_modules', 'svg-bbox', 'config');
      expect(fs.existsSync(configDir)).toBe(true);
    });

    it('should have version.cjs file', () => {
      const versionPath = path.join(testDir, 'node_modules', 'svg-bbox', 'version.cjs');
      expect(fs.existsSync(versionPath)).toBe(true);
    });
  });

  describe('Version Verification', () => {
    it('should have correct version in package.json', () => {
      const pkgJsonPath = path.join(testDir, 'node_modules', 'svg-bbox', 'package.json');
      const pkgJson = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf8'));
      expect(pkgJson.version).toBe(VERIFY_NPM_VERSION);
    });

    it('should have correct version in version.cjs', () => {
      const versionPath = path.join(testDir, 'node_modules', 'svg-bbox', 'version.cjs');
      // Use spawnSync to execute node and check version
      const result = spawnSync(
        'node',
        ['-e', `console.log(require('${versionPath}').getVersion())`],
        {
          cwd: testDir,
          encoding: 'utf8'
        }
      );
      expect(result.status).toBe(0);
      expect(result.stdout.trim()).toBe(VERIFY_NPM_VERSION);
    });
  });

  describe('Library Import', () => {
    it('should be require()-able without errors', () => {
      const result = spawnSync(
        'node',
        [
          '-e',
          `
        const lib = require('svg-bbox');
        console.log(typeof lib.getSvgElementVisualBBoxTwoPassAggressive);
      `
        ],
        {
          cwd: testDir,
          encoding: 'utf8'
        }
      );
      expect(result.status).toBe(0);
      expect(result.stdout.trim()).toBe('function');
    });

    it('should export getSvgElementsUnionVisualBBox function', () => {
      const result = spawnSync(
        'node',
        [
          '-e',
          `
        const lib = require('svg-bbox');
        console.log(typeof lib.getSvgElementsUnionVisualBBox);
      `
        ],
        {
          cwd: testDir,
          encoding: 'utf8'
        }
      );
      expect(result.status).toBe(0);
      expect(result.stdout.trim()).toBe('function');
    });

    it('should export getSvgElementVisibleAndFullBBoxes function', () => {
      const result = spawnSync(
        'node',
        [
          '-e',
          `
        const lib = require('svg-bbox');
        console.log(typeof lib.getSvgElementVisibleAndFullBBoxes);
      `
        ],
        {
          cwd: testDir,
          encoding: 'utf8'
        }
      );
      expect(result.status).toBe(0);
      expect(result.stdout.trim()).toBe('function');
    });

    it('should export getSvgRootViewBoxExpansionForFullDrawing function', () => {
      const result = spawnSync(
        'node',
        [
          '-e',
          `
        const lib = require('svg-bbox');
        console.log(typeof lib.getSvgRootViewBoxExpansionForFullDrawing);
      `
        ],
        {
          cwd: testDir,
          encoding: 'utf8'
        }
      );
      expect(result.status).toBe(0);
      expect(result.stdout.trim()).toBe('function');
    });
  });

  describe('CLI Tool Bin Symlinks', () => {
    it('should have node_modules/.bin directory', () => {
      expect(fs.existsSync(binDir)).toBe(true);
    });

    // Test each CLI tool has a working symlink
    for (const tool of CLI_TOOLS) {
      it(`should have ${tool} symlink in .bin/`, () => {
        const toolPath = path.join(binDir, tool);
        // On Windows, npm creates .cmd files instead of symlinks
        const exists = fs.existsSync(toolPath) || fs.existsSync(toolPath + '.cmd');
        expect(exists).toBe(true);
      });
    }
  });

  describe('CLI Tool --help Execution', () => {
    // Test each CLI tool responds to --help
    for (const tool of CLI_TOOLS) {
      it(`${tool} --help should exit with code 0`, () => {
        const toolPath = path.join(binDir, tool);
        const result = spawnSync('node', [toolPath, '--help'], {
          cwd: testDir,
          encoding: 'utf8',
          timeout: 10000
        });

        // Some tools might use process.exit(0) for --help
        expect(result.status).toBe(0);
      });
    }
  });

  describe('CLI Tool --version Execution', () => {
    // Test key CLI tools show correct version
    const versionTools = ['svg-bbox', 'sbb-getbbox', 'sbb-test'];

    for (const tool of versionTools) {
      it(`${tool} --version should show ${VERIFY_NPM_VERSION}`, () => {
        const toolPath = path.join(binDir, tool);
        const result = spawnSync('node', [toolPath, '--version'], {
          cwd: testDir,
          encoding: 'utf8',
          timeout: 10000
        });

        expect(result.status).toBe(0);
        expect(result.stdout).toContain(VERIFY_NPM_VERSION);
      });
    }
  });

  describe('Minified Library Validation', () => {
    it('should have valid JavaScript in SvgVisualBBox.min.js', () => {
      const minPath = path.join(testDir, 'node_modules', 'svg-bbox', 'SvgVisualBBox.min.js');
      const result = spawnSync('node', ['--check', minPath], {
        cwd: testDir,
        encoding: 'utf8'
      });
      expect(result.status).toBe(0);
    });

    it('should have version comment in minified file', () => {
      const minPath = path.join(testDir, 'node_modules', 'svg-bbox', 'SvgVisualBBox.min.js');
      const content = fs.readFileSync(minPath, 'utf8');
      // Check for version in preamble comment
      expect(content).toContain(VERIFY_NPM_VERSION);
    });
  });
});

// Export for potential reuse
export { CLI_TOOLS, VERIFY_NPM_VERSION };
