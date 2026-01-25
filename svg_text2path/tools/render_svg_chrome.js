#!/usr/bin/env node
/**
 * Render SVG to PNG using Puppeteer/Chrome
 *
 * Usage: node render_svg_chrome.js input.svg output.png width height
 * The height and width must be the same of the svg document!
 */

const puppeteer = require('puppeteer');
const fs = require('fs');

async function renderSvg(svgPath, outputPath, width, height) {
    // Read SVG file
    const svgContent = fs.readFileSync(svgPath, 'utf8');

    // Launch browser
    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    try {
        const page = await browser.newPage();

        // Set viewport
        await page.setViewport({ width, height });

        // Create HTML wrapper for SVG
        const html = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {
            margin: 0;
            padding: 0;
            background: white;
            display: flex;
            justify-content: center;
            align-items: center;
            width: ${width}px;
            height: ${height}px;
        }
        svg {
            max-width: 100%;
            max-height: 100%;
        }
    </style>
</head>
<body>
${svgContent}
</body>
</html>
        `;

        // Load SVG
        await page.setContent(html, { waitUntil: 'networkidle0' });

        // Wait for rendering using new API
        await new Promise(resolve => setTimeout(resolve, 500));

        // Take screenshot
        await page.screenshot({
            path: outputPath,
            fullPage: false,
            type: 'png'
        });

        console.log(`✓ Rendered: ${outputPath}`);

    } finally {
        await browser.close();
    }
}

// Parse command line arguments
const args = process.argv.slice(2);
if (args.length < 2) {
    console.error('Usage: node render_svg_chrome.js input.svg output.png width height\nThe width and height must be the same of the svg document!');
    process.exit(1);
}

const [svgPath, outputPath, width, height] = args;

renderSvg(
    svgPath,
    outputPath,
    parseInt(width),
    parseInt(height)
).catch(err => {
    console.error('Error:', err);
    process.exit(1);
});
