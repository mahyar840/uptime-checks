// Panel relay: a real Chromium on the GitHub runner, logged in to the Torob seller panel with cookies
// that the Cloudflare worker hands out only after verifying this job's GitHub OIDC token.
// It pulls queued panel commands from the worker, runs them in the logged-in page and posts results back.
// Never prints cookies, command bodies or results — only counts.
import { chromium } from 'playwright';

const W = process.env.W;
const DUR = Number(process.env.DUR_MIN || 45) * 60000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const t0 = Date.now();

async function oidc() {
  const r = await fetch(process.env.ACTIONS_ID_TOKEN_REQUEST_URL + '&audience=torob-panel-probe', {
    headers: { Authorization: 'bearer ' + process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN },
  });
  return (await r.json()).value;
}

const sr = await fetch(W + '/gh-oidc/session' + (process.env.AUTO === '1' ? '?auto=1' : ''), { method: 'POST', headers: { Authorization: 'Bearer ' + (await oidc()) } });
if (sr.status === 409) { console.log('skip: ' + (await sr.text())); process.exit(0); }
if (sr.status !== 200) { console.log('session failed status=' + sr.status); process.exit(1); }
const sess = await sr.json();
const H = { 'x-relay-key': sess.key, 'Content-Type': 'application/json' };
const post = async (path, body) => {
  for (let i = 0; i < 3; i++) {
    try { const r = await fetch(W + path, { method: 'POST', headers: H, body: JSON.stringify(body || {}) }); return await r.json(); }
    catch (e) { await sleep(1500); }
  }
  return {};
};

const cookies = (sess.cookies || []).filter((c) => /torob\.com$/.test(c.domain || '')).map((c) => ({
  name: c.name, value: c.value, domain: c.domain, path: c.path || '/',
  expires: (c.session || !c.expires || c.expires < 0) ? -1 : Math.floor(c.expires),
  httpOnly: !!c.httpOnly, secure: !!c.secure, sameSite: 'Lax',
}));
console.log(`cookies loaded: ${cookies.length}`);

const browser = await chromium.launch();
const ctx = await browser.newContext({
  locale: 'fa-IR',
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
});
await ctx.addCookies(cookies);
const page = await ctx.newPage();
try { await page.goto('https://panel.torob.com/t?instance_id=376', { waitUntil: 'domcontentloaded', timeout: 45000 }); } catch (e) {}
await page.waitForTimeout(4000);
console.log('panel landed: ' + new URL(page.url()).host + new URL(page.url()).pathname);

const stats = { done: 0, errors: 0, polls: 0 };
let lastCk = Date.now();
while (Date.now() - t0 < DUR) {
  stats.polls++;
  const job = await post('/gh-oidc/next', { hb: stats.polls % 10 === 1 });
  if (!job || !job.id) { await sleep(1000); continue; }
  let res, ck = null;
  try {
    const req = JSON.parse(job.req);
    if (req.navigate) {
      await page.goto(req.navigate, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(req.wait || 4000);
    }
    let value = null;
    if (req.expr) value = await page.evaluate(req.expr);
    if (req.saveCookies || Date.now() - lastCk > 10 * 60000) { ck = await ctx.cookies(); lastCk = Date.now(); }
    res = { ok: true, value, cookies: ck ? ck.length : null };
    stats.done++;
  } catch (e) {
    res = { error: String((e && e.message) || e).split('\n')[0].slice(0, 300) };
    stats.errors++;
  }
  await post('/gh-oidc/done', { id: job.id, res, cookies: ck });
}
const final = await ctx.cookies();
await post('/gh-oidc/stop', { stats: { ...stats, min: Math.round((Date.now() - t0) / 60000) } });
await browser.close();
console.log(`relay finished: done=${stats.done} errors=${stats.errors} polls=${stats.polls} cookies_now=${final.length}`);
