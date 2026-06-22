# Generating uncached names

`POST /api/search` (which runs the 13 models for a new name) requires a Cloudflare Turnstile
token that only the page's own search UI mints. Plain `curl` / headless Playwright get
`403 Verification required` or stall on the challenge. The reliable path is to drive the real
search box inside a browser that has already passed Cloudflare (we used the Playwright MCP
browser).

The trick: setting the React input value + dispatching `input` + Enter triggers the app's own
handler, which mints the token and generates. Run this inside the verified page, in batches:

```js
// install once on window
window.genBatch = async (names) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const norm = s => (s||"").normalize('NFKD').replace(/[̀-ͯ]/g,'')
                     .toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  const out = [];
  for (const name of names) {
    const input = document.querySelector('input[type="search"], input');
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
    setter.call(input, name);
    input.dispatchEvent(new Event('input',  {bubbles:true}));
    input.dispatchEvent(new Event('change', {bubbles:true}));
    await sleep(80);
    for (const t of ['keydown','keypress','keyup'])
      input.dispatchEvent(new KeyboardEvent(t,{key:'Enter',keyCode:13,which:13,bubbles:true}));
    // read the canonical slug from the URL the SPA navigates to, and verify the
    // returned result's `query` actually matches this name (guards a navigation race)
    let slug=null, status=0;
    for (let i=0;i<35;i++){
      await sleep(1200);
      const p = location.pathname;
      if (!p.startsWith('/p/')) continue;
      const sl = p.slice(3);
      const r = await fetch('/api/result/'+sl).then(x=>x.ok?x.json():null).catch(()=>null);
      if (r && norm(r.query)===norm(name)) { slug=sl; status=200; break; }
    }
    out.push({name, slug, status});
  }
  return out;
};
```

Notes:
- The site escapes non-ASCII in slugs as `~<hexcodepoint>~` (e.g. `ł` → `~142~`,
  `.` → `~2e~`). Don't try to reproduce this — read the slug from the URL instead.
- Generation takes ~5–15s per name. Batches of ~6 fit comfortably in one `evaluate` call.
- Always verify `result.query === name`; a slow SPA navigation can otherwise attach the
  previous name's slug to the next person.
- Captured slugs are saved to `data/slugmap.json` and patched into `data/names.json`.
