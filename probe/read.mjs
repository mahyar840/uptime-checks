import { chromium } from 'playwright';
const ids = ["a2443db0-13f1-4b45-a241-0cac4bbe2a20","a7cb598b-f15c-470c-af35-209229028b86","983f7b8f-c983-43cc-a0ec-c3df65903a3c","7a9181bb-0129-4caf-8258-3f29bf70633c","66f38c04-7763-4d28-a0e1-35e0e757b8e7","b430c2bd-2d85-4956-baad-5c865c2a61c4","176a2664-9096-453d-a953-4930597e4cf3","864a937e-1cf5-48c1-a64a-20d11537bdd4","f3d924f1-232f-4bdb-a187-48a8d68c0bc7","d2343e8d-7769-450d-beea-8f2c84ec7d50"];
const t0 = Date.now();
const b = await chromium.launch();
const ctx = await b.newContext({ locale: 'fa-IR', userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36' });
const p = await ctx.newPage();
const res = [];
for (const id of ids) {
  const s = Date.now(); let st = 0, kind = 'ok', title = '', err = '';
  try {
    const r = await p.goto(`https://torob.com/p/${id}/`, { waitUntil: 'domcontentloaded', timeout: 45000 });
    st = r ? r.status() : 0;
    await p.waitForTimeout(1500);
    const html = (await p.content()).toLowerCase();
    title = (await p.title()).slice(0, 60);
    if (st === 403 || st === 429) kind = 'blocked';
    else if (/captcha|arcaptcha|challenge|cf-chl|access denied|too many requests/.test(html)) kind = 'captcha';
    else if (st >= 400) kind = 'http' + st;
    else if (!/<h1/.test(html)) kind = 'no-h1';
  } catch (e) { kind = 'error'; err = String(e.message).split('\n')[0].slice(0, 100); }
  res.push({ id: id.slice(0, 8), st, kind, ms: Date.now() - s, title, err });
  console.log(JSON.stringify(res.at(-1)));
  await p.waitForTimeout(4000 + Math.floor(Math.random() * 4000));
}
await b.close();
const ok = res.filter(r => r.kind === 'ok').length;
console.log(`SUMMARY ok=${ok}/${res.length} blocked=${res.filter(r=>r.kind==='blocked'||r.kind==='captcha').length} total_s=${Math.round((Date.now()-t0)/1000)}`);
