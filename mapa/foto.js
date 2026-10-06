// Toma la foto del póster: completa (PNG grande) y reducida (para ver en el teléfono).
const puppeteer = require('puppeteer-core');
(async () => {
  const b = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.setViewport({ width: 3200, height: 1000, deviceScaleFactor: 1 });
  await p.goto('file://' + process.cwd() + '/poster.html', { waitUntil: 'networkidle0' });
  await p.evaluate(() => document.fonts.ready);
  await p.screenshot({ path: 'ecosistema-n8n.png', fullPage: true });
  await p.setViewport({ width: 3200, height: 1000, deviceScaleFactor: 0.5 });
  await p.screenshot({ path: 'ecosistema-chico.jpg', type: 'jpeg', quality: 88, fullPage: true });
  await b.close();
})();
