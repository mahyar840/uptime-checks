import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import crypto from 'node:crypto';
// Decrypt hybrid blob (RSA-OAEP-SHA256 wrapped AES-256-GCM). Cookie values are never printed.
const priv = readFileSync(process.env.KEY_FILE, 'utf8');
const blob = JSON.parse(readFileSync(process.env.BLOB_FILE, 'utf8'));
const aesKey = crypto.privateDecrypt({ key: priv, padding: crypto.constants.RSA_PKCS1_OAEP_PADDING, oaepHash: 'sha256' }, Buffer.from(blob.k, 'base64'));
const ct = Buffer.from(blob.c, 'base64');
const d = crypto.createDecipheriv('aes-256-gcm', aesKey, Buffer.from(blob.iv, 'base64'));
d.setAuthTag(ct.subarray(ct.length - 16));
const raw = JSON.parse(Buffer.concat([d.update(ct.subarray(0, ct.length - 16)), d.final()]).toString('utf8'));
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
