/* Browser acceptance on local fixture server only. Usage: node file playwrightModule chromePath baseURL outputDir */
const assert=require('node:assert/strict');
const {chromium}=require(process.argv[2]);
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[3],headless:true});
 try {
 const page=await browser.newPage(); const base=process.argv[4], output=process.argv[5];
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 for(const width of [1440,900,390]){
  await page.setViewportSize({width,height:1000});
  for(const name of ['overview','installations','providers','provider','statistics','device','health']){
   await page.goto(base+'/admin/'+name+'.html');await page.waitForTimeout(150);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${name}/${width}: page overflow`);
   assert.deepEqual(errors.splice(0),[],`${name}/${width}: script errors`);
   assert(!/\bFresh\b/i.test(await page.locator('main').innerText()), `${name}: no Fresh labels`);
   if(name==='health'){
    const boxes=await page.locator('[data-health-status]').evaluateAll(es=>es.slice(0,4).map(e=>({x:e.offsetLeft,y:e.offsetTop})));
    const columns=width===1440?3:width===900?2:1;
    assert.equal(boxes.filter(b=>b.y===boxes[0].y).length,columns,`health/${width}: expected columns`);
   }
   if(name==='overview'){
    const metrics=await page.locator('.overview-map-total').evaluateAll(es=>es.map(e=>({height:e.getBoundingClientRect().height,font:getComputedStyle(e.querySelector('strong')).fontSize,weight:getComputedStyle(e.querySelector('strong')).fontWeight})));
    assert.equal(new Set(metrics.map(m=>m.height)).size,1,'Chart totals share height');
    assert.equal(new Set(metrics.map(m=>m.font)).size,1,'Chart totals share numeric size');
    assert.equal(new Set(metrics.map(m=>m.weight)).size,1,'Chart totals share numeric weight');
    assert.equal(await page.locator('.overview-kpis .map-statistics-kpi-value.failed').first().evaluate(e=>getComputedStyle(e).borderTopWidth),'1px');
   }
   if(name==='installations'){
    const fonts=await page.locator('#evidence-rows tr').first().evaluate(e=>[3,4,5,6].map(i=>getComputedStyle(e.children[i].querySelector('.admin-error-counter')||e.children[i].querySelector('a')||e.children[i]).fontSize));
    assert.equal(new Set(fonts).size,1,'Installation numbers share size');
    assert.equal(await page.locator('.installation-kpis .failed').evaluate(e=>getComputedStyle(e).borderTopWidth),'1px');
   }
   if(name==='device'){
    assert.equal(await page.locator('.attempts-metric>span').evaluate(e=>getComputedStyle(e,'::after').content),'none');
    assert.equal(await page.locator('.map-statistics-kpi-secondary').evaluate(e=>getComputedStyle(e).borderTopWidth),'1px');
   }
   if(name==='statistics'){
    assert.match(await page.locator('#map-statistics-world-map-status').innerText(),/15 Custom maps/);
    assert.match(await page.locator('#map-statistics-world-map-status').innerText(),/1 installs without country coverage/);
    assert.match(await page.locator('.download-time').first().innerText(),/downloads/);
   }
   if(['overview','installations','device','statistics'].includes(name)){
    const selector=name==='statistics'?'.map-statistics-kpi-value:not(.failed)>strong':'.admin-kpi-panel .map-statistics-kpi-value:not(.failed):not(.timestamp-metric)>strong';
    assert.equal(await page.locator(selector).first().evaluate(e=>getComputedStyle(e).fontSize),'24px',`${name}: shared KPI size`);
   }

   await page.screenshot({path:`${output}/${name}-${width}.png`,fullPage:true});
  }
  await page.goto(base+'/admin/device.html');
  const empty=page.locator('td[colspan]').first();
  assert.equal(await empty.evaluate(e=>getComputedStyle(e).textAlign),'center');
  if(width===390)assert.equal(await empty.evaluate(e=>getComputedStyle(e).gridColumn),'1 / -1');
  for(const label of ['Administration','Device information','Technical details']){
   const summary=page.getByText(label,{exact:true}).filter({hasNot:page.locator('h1')}).first();
   await summary.focus(); await page.keyboard.press('Space');
   assert.equal(await summary.evaluate(e=>e.parentElement.open),label==='Administration'?false:true);
   assert.equal(await summary.evaluate(e=>Math.round(e.getBoundingClientRect().height)),44,label+' shared height');
  }
 }
 await page.setViewportSize({width:1440,height:1000});
 await page.goto(base+'/admin/installations.html');
 for(const key of ['model','variant','status','attempts','successfulCount','failedCount','errors','lastSuccess']){
  const button=page.locator(`[data-installation-sort="${key}"]`);await button.focus();await page.keyboard.press('Enter');
  assert.equal(await button.locator('..').getAttribute('aria-sort'),'ascending');
  assert.equal(await page.locator('#evidence-sort').inputValue(),key+':ascending');
  await page.keyboard.press('Space');assert.equal(await button.locator('..').getAttribute('aria-sort'),'descending');
 }
 await page.locator('[data-installation-sort="model"]').click();
 let names=await page.locator('#evidence-rows tr:not([hidden])').evaluateAll(es=>es.map(e=>e.dataset.model));
 assert.match(names[0],/fēnix 1 /); assert.match(names[1],/fēnix 2 /); assert.equal(names.length,120);
 await page.locator('[data-installation-sort="lastSuccess"]').click();
 let dates=await page.locator('#evidence-rows tr:not([hidden])').evaluateAll(es=>es.map(e=>e.dataset.lastSuccess));
 assert.equal(dates.at(-1),'');
 await page.locator('[data-installation-sort="lastSuccess"]').click();
 dates=await page.locator('#evidence-rows tr:not([hidden])').evaluateAll(es=>es.map(e=>e.dataset.lastSuccess));assert.equal(dates.at(-1),'');
 await page.locator('#evidence-search').fill('fēnix 12 Very');assert.equal(await page.locator('#evidence-rows tr:not([hidden])').count(),1);
 assert.match(page.url(),/search=/);await page.reload();assert.equal(await page.locator('#evidence-search').inputValue(),'fēnix 12 Very');
 await page.goto(base+'/admin/health.html');await page.locator('#health-status').selectOption('FAILED');
 assert.equal(await page.locator('[data-health-status]:not([hidden])').count(),5);
 await page.locator('#health-search').fill('Check 2');assert.equal(await page.locator('[data-health-status]:not([hidden])').count(),1);
 await page.locator('[data-health-status]:not([hidden]) summary').focus();await page.keyboard.press('Enter');
 assert.equal(await page.locator('[data-health-status]:not([hidden])').getAttribute('open'),'');
 await page.goto(base+'/admin/providers.html');const providerTime=await page.locator('.download-time').first().innerText();
 await page.goto(base+'/admin/statistics.html');assert.equal(await page.locator('.download-time').first().innerText(),providerTime);
 const timing=page.locator('#provider-statistic-rows td').last();
 assert(await timing.evaluate(e=>e.getBoundingClientRect().right <= innerWidth), 'Duration column visible on desktop');
 // Polling is controlled without sleeping: the real installed handler runs against a routed snapshot.
 const refresh=await browser.newPage();await refresh.addInitScript(()=>{const original=setInterval;window.setInterval=(f,ms)=>ms===60000?(window.testPoll=f,1):original(f,ms);});
 await refresh.goto(base+'/admin/device.html');await refresh.waitForFunction(()=>!!window.testPoll);
 const originalHTML=await (await refresh.request.get(base+'/admin/device.html')).text();
 let snapshot=await refresh.locator('main').getAttribute('data-admin-revisions');let mode='ok';let release;let requests=0;
 await refresh.route('**/admin/device.html',async route=>{
  requests++;
  if(mode==='offline')return route.abort();
  if(mode==='session')return route.fulfill({status:401,body:''});
  if(mode==='delayed')await new Promise(r=>release=r);
  await route.fulfill({status:200,contentType:'text/html',body:originalHTML.replace(/data-admin-revisions="[^"]*"/,`data-admin-revisions='${snapshot}'`)});
 });
 const poll=()=>refresh.evaluate(()=>window.testPoll());const notice=refresh.locator('#admin-live-update');
 await poll();assert.equal(await notice.isVisible(),false);
 const beforeHidden=requests;await refresh.evaluate(()=>Object.defineProperty(document,'hidden',{configurable:true,value:true}));
 await poll();assert.equal(requests,beforeHidden);await refresh.evaluate(()=>delete document.hidden);
 const initial=JSON.parse(snapshot);snapshot=JSON.stringify({...initial,device:'changed',diagnostics:'changed'});
 await poll();assert.equal(await notice.isVisible(),true);
 await refresh.evaluate(()=>window.dispatchEvent(new CustomEvent('terento-admin-sections-rendered',{detail:{device:'changed'}})));
 assert.equal(await notice.isVisible(),true,'Other unseen section remains pending');
 await refresh.evaluate(()=>window.dispatchEvent(new CustomEvent('terento-admin-sections-rendered',{detail:{diagnostics:'changed'}})));
 assert.equal(await notice.isVisible(),false);await poll();assert.equal(await notice.isVisible(),false);
 await refresh.locator('form[method="post"] textarea').first().fill('unsaved');
 snapshot=JSON.stringify({...initial,device:'next'});await poll();
 let asked=false;refresh.once('dialog',async dialog=>{asked=true;await dialog.dismiss();});
 await notice.getByRole('button',{name:'Refresh'}).click();assert(asked);assert.equal(await refresh.locator('form[method="post"] textarea').first().inputValue(),'unsaved');
 mode='offline';await poll();assert.match(await notice.innerText(),/unavailable/i);
 mode='session';await poll();assert.match(await notice.innerText(),/session expired/i);
 mode='delayed';const waiting=poll();await new Promise(r=>setTimeout(r,50));
 const beforeOverlap=requests;await poll();assert.equal(requests,beforeOverlap);
 await refresh.evaluate(()=>{history.replaceState(null,'','?changed=1');window.dispatchEvent(new Event('terento-admin-content-changed'));});
 release();await waiting;assert.equal(await notice.isVisible(),false,'Old URL response ignored');
 mode='ok';await refresh.evaluate(()=>history.replaceState(null,'','/admin/device.html'));
 snapshot=JSON.stringify({...initial,device:'final'});await poll();assert.equal(await notice.isVisible(),true);
 refresh.once('dialog',dialog=>dialog.accept());
 await Promise.all([refresh.waitForNavigation(),notice.getByRole('button',{name:'Refresh'}).click()]);
 await refresh.waitForFunction(()=>!!window.testPoll);await poll();assert.equal(await notice.isVisible(),false);
 console.log('PASS: 21 responsive pages, sorting all 120 identities, unknown dates both directions, persisted filters, disclosure keyboard/44px geometry, 50 health checks, metric parity, section acknowledgements, dirty form, session/network errors and stale polling response.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
