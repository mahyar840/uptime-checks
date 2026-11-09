import { chromium } from 'playwright';
// Cookies come from the TOROB_COOKIES secret (JSON array). Values are never printed.
const raw = JSON.parse(process.env.TOROB_COOKIES);
const cookies = raw.filter(c => /torob\.com$/.test(c.domain)).map(c => ({
  name: c.name, value: c.value, domain: c.domain, path: c.path || '/',
  expires: (c.session || !c.expires || c.expires < 0) ? -1 : Math.floor(c.expires),
  httpOnly: !!c.httpOnly, secure: !!c.secure, sameSite: 'Lax',
}));
console.log(`cookies loaded: ${cookies.length} (names hidden)`);
const b = await chromium.launch();
const ctx = await b.newContext({ locale: 'fa-IR', userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36' });
await ctx.addCookies(cookies);
const p = await ctx.newPage();
let nav = 0;
try { const r = await p.goto('https://panel.torob.com/t?instance_id=376', { waitUntil: 'domcontentloaded', timeout: 45000 }); nav = r ? r.status() : 0; }
catch (e) { console.log('panel nav error: ' + String(e.message).split('\n')[0].slice(0, 120)); }
await p.waitForTimeout(4000);
const u = new URL(p.url());
console.log(`panel nav status=${nav} landed=${u.host}${u.pathname}`);
// Read-only GET only. Report status code (and JSON top-level keys, no values).
const out = await p.evaluate(async () => {
  try {
    const r = await fetch('https://api.torob.com/matching/v2/cs/shop/info/?instance_id=376', { credentials: 'include' });
    let keys = '';
    try { const j = await r.clone().json(); keys = Object.keys(j || {}).slice(0, 10).join(','); } catch {}
    return { status: r.status, keys };
  } catch (e) { return { status: -1, err: String(e).slice(0, 120) }; }
});
console.log('SHOP_INFO ' + JSON.stringify(out));
await b.close();
