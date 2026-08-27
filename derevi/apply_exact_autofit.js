const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const CARD_FILE = path.join(ROOT, 'derevi_cards.cardconjurer');
const AUDIT_FILE = path.join(ROOT, 'ART_FIT_AUDIT.md');
const STATUS_FILE = path.join(ROOT, 'PROXY_SYNC_STATUS.md');

function pngDimensions(filePath) {
  const b = fs.readFileSync(filePath);
  if (b.length < 24 || b.toString('hex', 0, 8) !== '89504e470d0a1a0a') {
    throw new Error(`Not a PNG: ${filePath}`);
  }
  return { width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
}

function autoFit(card, imageWidth, imageHeight) {
  // These deliberately mirror Card Conjurer's own scale helpers and autoFitArt().
  const scaleX = input => Math.round((input + card.marginX) * card.width);
  const scaleWidth = input => Math.round(input * card.width);
  const scaleY = input => Math.round((input + card.marginY) * card.height);
  const scaleHeight = input => Math.round(input * card.height);

  const bounds = card.artBounds;
  const boxW = scaleWidth(bounds.width);
  const boxH = scaleHeight(bounds.height);
  let xPx, yPx, zoomPercent;

  if (imageWidth / imageHeight > boxW / boxH) {
    yPx = Math.round(scaleY(bounds.y) - scaleHeight(card.marginY));
    zoomPercent = (boxH / imageHeight * 100).toFixed(1);
    xPx = Math.round(
      scaleX(bounds.x)
      - ((zoomPercent / 100 * imageWidth) - boxW) / 2
      - scaleWidth(card.marginX)
    );
  } else {
    xPx = Math.round(scaleX(bounds.x) - scaleWidth(card.marginX));
    zoomPercent = (boxW / imageWidth * 100).toFixed(1);
    yPx = Math.round(
      scaleY(bounds.y)
      - ((zoomPercent / 100 * imageHeight) - boxH) / 2
      - scaleHeight(card.marginY)
    );
  }

  return {
    xPx,
    yPx,
    artX: xPx / card.width,
    artY: yPx / card.height,
    artZoom: Number(zoomPercent) / 100,
    zoomPercent: Number(zoomPercent),
    boxW,
    boxH,
  };
}

const cards = JSON.parse(fs.readFileSync(CARD_FILE, 'utf8'));
if (!Array.isArray(cards) || cards.length === 0) throw new Error('No cards found');

const referenceNames = new Set([
  'Derevi, Empyrial Tactician',
  'Cloud, Midgar Mercenary',
  'Delney, Streetwise Lookout',
]);
const referenceExpected = {
  artX: 0.035323383084577116,
  artY: 0.11300639658848614,
  artZoom: 1.217,
};

const rows = [];
let referenceChecked = 0;
for (const entry of cards) {
  const card = entry.data;
  const artSource = card.artSource || '';
  const filename = decodeURIComponent(artSource.split('/').pop() || '');
  const filePath = path.join(ROOT, filename);
  if (!filename || !fs.existsSync(filePath)) {
    throw new Error(`${entry.key}: art file not found for ${artSource}`);
  }

  const { width, height } = pngDimensions(filePath);
  const fit = autoFit(card, width, height);

  if (referenceNames.has(entry.key)) {
    referenceChecked++;
    if (
      fit.artX !== referenceExpected.artX ||
      fit.artY !== referenceExpected.artY ||
      fit.artZoom !== referenceExpected.artZoom
    ) {
      throw new Error(
        `${entry.key}: exact autofit verification failed. ` +
        `Calculated ${fit.artX}, ${fit.artY}, ${fit.artZoom}; ` +
        `expected ${referenceExpected.artX}, ${referenceExpected.artY}, ${referenceExpected.artZoom}`
      );
    }
  }

  card.artX = fit.artX;
  card.artY = fit.artY;
  card.artZoom = fit.artZoom;
  card.artRotate = '0';
  // Values are now stored directly; no on-load script is needed.
  card.onload = null;

  rows.push({
    name: entry.key,
    filename,
    width,
    height,
    xPx: fit.xPx,
    yPx: fit.yPx,
    artX: fit.artX,
    artY: fit.artY,
    artZoom: fit.artZoom,
  });
}

if (referenceChecked !== 3) throw new Error(`Only checked ${referenceChecked}/3 reference cards`);

fs.writeFileSync(CARD_FILE, JSON.stringify(cards), 'utf8');

const audit = [
  '# Exact Card Conjurer art-fit audit',
  '',
  `- Cards recalculated: **${rows.length}**`,
  '- Algorithm: exact reproduction of Card Conjurer `autoFitArt()` including pixel rounding and `toFixed(1)` zoom rounding.',
  '- Reference check: **PASS**. Derevi, Cloud, and Delney reproduce the exact values saved by the official Auto Fit button.',
  `- Reference result: artX = \`${referenceExpected.artX}\`, artY = \`${referenceExpected.artY}\`, artZoom = \`${referenceExpected.artZoom}\`.`,
  '- All calculated values are now stored directly in `derevi_cards.cardconjurer`; `onload` is cleared.',
  '',
  '| Card | PNG size | X px | Y px | artX | artY | artZoom |',
  '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
];
for (const r of rows) {
  audit.push(`| ${r.name.replace(/\|/g, '\\|')} | ${r.width}×${r.height} | ${r.xPx} | ${r.yPx} | ${r.artX} | ${r.artY} | ${r.artZoom} |`);
}
fs.writeFileSync(AUDIT_FILE, audit.join('\n') + '\n', 'utf8');

let status = fs.existsSync(STATUS_FILE) ? fs.readFileSync(STATUS_FILE, 'utf8').trimEnd() : '# Derevi proxy sync status';
if (status.includes('## Exact art-fit audit')) {
  status = status.split('## Exact art-fit audit')[0].trimEnd();
}
status += `\n\n## Exact art-fit audit\n- Cards recalculated from actual PNG dimensions: **${rows.length}**.\n- Official Auto Fit reference cards reproduced exactly: **3/3**.\n- Art-fit mismatches remaining: **0**.\n- Stored numeric placement is used; no card requires the on-load auto-fit script.\n- See \`ART_FIT_AUDIT.md\` for every image dimension and calculated value.\n`;
fs.writeFileSync(STATUS_FILE, status, 'utf8');

console.log(`Updated ${rows.length} cards.`);
console.log('Reference verification PASS for Derevi, Cloud, and Delney.');
for (const r of rows) {
  console.log(`${r.name}: ${r.width}x${r.height} -> X=${r.artX} Y=${r.artY} Zoom=${r.artZoom}`);
}
