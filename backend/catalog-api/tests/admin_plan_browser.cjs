/* Browser acceptance on local fixture server only. Usage: node file playwrightModule chromePath baseURL outputDir */
const assert=require('node:assert/strict');
const {chromium}=require(process.argv[2]);
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[3],headless:true});
 try {
 const page=await browser.newPage(); const base=process.argv[4], output=process.argv[5];
 const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
 for(const width of [1440,1024,720,390]){
  await page.setViewportSize({width,height:1000});
  for(const name of ['overview','installations','providers','provider','statistics','device','health','diagnostics','identification','identification-ambiguous','identification-decided','identification-no-others']){
   await page.goto(base+'/admin/'+name+'.html');await page.waitForTimeout(150);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${name}/${width}: page overflow`);
   assert.deepEqual(errors.splice(0),[],`${name}/${width}: script errors`);
   assert(!/\bFresh\b/i.test(await page.locator('main').innerText()), `${name}: no Fresh labels`);
   if(name==='health'){
    const indexnow=page.locator("[data-health-name='indexnow submissions']");
    assert.equal(await indexnow.count(),1,'one IndexNow card');
    const indexnowSummary=indexnow.locator('.system-health-issue-heading');
    assert.equal(await indexnowSummary.locator('h2').innerText(),'IndexNow submissions');
    assert.equal(await indexnowSummary.locator('.system-health-badge').count(),1,'IndexNow summary has one health badge');
    assert.equal(await indexnowSummary.locator('.health-issue').count(),0,'IndexNow summary has no result detail');
    assert(!/Last check|Pending URLs|Validation pending/i.test(await indexnowSummary.innerText()),'IndexNow summary has no expanded details');
    const indexnowTechnical=indexnow.locator('details.system-health-technical');
    await indexnowTechnical.locator('summary').click();
    assert.match(await indexnow.locator('.disclosure-body').innerText(),/validation message remains readable/);
    assert.match(await indexnow.locator('.disclosure-body').innerText(),/https:\/\/terento\.app\/guides\/install-garmin-maps-mac\//);
    assert.equal(await page.locator('[data-health-name]').first().locator('.system-health-cause').count(),1,'other health card keeps its summary issue');
   }
   if(name==='overview'){
    const metrics=await page.locator('.overview-map-total').evaluateAll(es=>es.map(e=>({height:e.getBoundingClientRect().height,font:getComputedStyle(e.querySelector('strong')).fontSize,weight:getComputedStyle(e.querySelector('strong')).fontWeight})));
    assert.equal(new Set(metrics.map(m=>m.height)).size,1,'Chart totals share height');
    assert.equal(new Set(metrics.map(m=>m.font)).size,1,'Chart totals share numeric size');
    assert.equal(new Set(metrics.map(m=>m.weight)).size,1,'Chart totals share numeric weight');
    assert.equal(await page.locator('.overview-download-panel').count(),1,'App downloads chart remains visible');
    assert.equal(await page.locator('.overview-download-panel h2').innerText(),'App downloads');
    assert.equal(await page.getByText('Observed GitHub .dmg and .zip counter increases.').count(),0,'App download explanation is removed');
    assert.deepEqual(await page.locator('main>.overview-primary-grid, main>.overview-composition-grid').evaluateAll(es=>es.map(e=>e.className)),['overview-primary-grid','overview-composition-grid']);
    assert.equal(await page.locator('.overview-map-total-scope').count(),0,'All-time scope is removed from visible badge copy');
    const mapBadges=page.locator('.overview-map-total');
    assert.equal(await mapBadges.count(),6,'Both map charts keep three summary badges');
    assert.equal(await mapBadges.evaluateAll(es=>es.every(e=>e.title==='All time')),true,'Every badge exposes all-time scope on hover');
    assert.equal(await mapBadges.evaluateAll(es=>es.every(e=>/all time/i.test(e.getAttribute('aria-label')||''))),true,'Every badge exposes all-time scope to assistive technology');
    const visibleTrendCharts=page.locator('.overview-primary-grid .overview-trend-chart:visible');
    assert.equal(await visibleTrendCharts.count(),2,'Both current trend charts remain visible');
    for(const chart of await visibleTrendCharts.all()){
     const ticks=await chart.locator('.overview-chart-grid').evaluateAll(lines=>lines.map(line=>Number(line.getAttribute('y1'))));
     assert.equal(ticks.length,5,'Trend chart has five grid bands');
     const gaps=ticks.slice(1).map((value,index)=>Math.round((ticks[index]-value)*10)/10);
     assert.equal(new Set(gaps).size,1,'Trend grid bands are evenly spaced');
    }
    const activityList=page.locator('.overview-activity-list');
    const activityGeometry=await activityList.evaluate(e=>({client:e.clientHeight,scroll:e.scrollHeight,overflow:getComputedStyle(e).overflowY,visible:[...e.children].filter(row=>row.getBoundingClientRect().top<e.getBoundingClientRect().bottom).length}));
    assert.equal(activityGeometry.overflow,'auto');
    assert(activityGeometry.scroll>activityGeometry.client,'Activity uses internal vertical scrolling');
    assert(activityGeometry.visible>=4&&activityGeometry.visible<=6,'Activity shows about four to six rows');
    const charts=await page.locator('.overview-primary-grid>.overview-panel').evaluateAll(es=>es.map(e=>e.getBoundingClientRect()));
    const attention=await page.locator('.overview-attention-panel').evaluate(e=>e.getBoundingClientRect());
    const activity=await page.locator('.overview-activity-panel').evaluate(e=>e.getBoundingClientRect());
    const app=await page.locator('.overview-download-panel').evaluate(e=>e.getBoundingClientRect());
    const appChart=await page.locator('.overview-download-panel .overview-trend-chart:visible').evaluate(svg=>{const panel=svg.closest('.overview-download-panel'),panelRect=panel.getBoundingClientRect(),rect=svg.getBoundingClientRect(),style=getComputedStyle(panel),viewBox=svg.viewBox.baseVal,innerWidth=panelRect.width-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight),scale=Math.min(rect.width/viewBox.width,rect.height/viewBox.height),offset=(rect.width-viewBox.width*scale)/2;return {innerWidth,renderedWidth:rect.width,leftUnused:offset+38*scale,rightUnused:innerWidth-(offset+(viewBox.width-12)*scale)}});
    assert(Math.abs(appChart.renderedWidth-appChart.innerWidth)<=3,'App downloads chart uses the card inner width');
    assert(appChart.leftUnused<55&&appChart.rightUnused<25,'App downloads chart keeps only axis and clipping margins');
    if(width>900){assert(Math.abs(charts[0].y-charts[1].y)<=1,'Dashboard charts share a row');assert(Math.abs(attention.y-activity.y)<=1,'Attention and Activity share a row');assert(app.y>=attention.y+attention.height+15,'App downloads follows Needs attention');assert(Math.abs(app.x-attention.x)<=1&&Math.abs(app.width-attention.width)<=1,'Left-column cards align');assert(Math.abs(activity.width-attention.width)<=1,'Dashboard composition columns match');assert(app.width<width*.6,'App downloads occupies half row');}
    else {assert(charts[1].y>charts[0].y,'Dashboard charts stack narrow');assert(activity.y>attention.y,'Activity follows Needs attention');assert(app.y>activity.y,'App downloads follows Activity');}
    assert.equal(await page.locator('.map-activity-row>a:not(.overview-activity-device)').count(),0,'Generic activity destinations are removed');
    if(width<=760){
     const toggle=page.locator('#admin-menu-toggle');
     assert.equal(await toggle.isVisible(),true,'Compact menu is available at 720px and narrower');
     await toggle.click();
     const primary=await page.locator('.admin-nav-group>a').allTextContents();
     assert.deepEqual(primary.map(value=>value.trim()),['Dashboard','Installations','Devices','Maps','Providers','Health']);
     assert.equal(await page.locator('.admin-nav-group').evaluate(e=>getComputedStyle(e).flexDirection),'column');
     assert.equal(await page.locator('.admin-nav').evaluate(e=>getComputedStyle(e).flexDirection),'column');
     const secondary=await page.locator('.admin-nav').evaluate(e=>[...e.children].map(child=>child.matches('.timezone-control')?'Timezone':child.matches('.admin-user')?child.textContent.trim():child.matches('.admin-mobile-website')?'Website':child.matches('form')?'Sign out':''));
     assert.deepEqual(secondary,['Timezone','Preview','Website','Sign out']);
     await page.screenshot({path:`${output}/menu-${width}.png`,fullPage:true});
     await toggle.click();
    }
   }
   if(name==='installations'){
    const fonts=await page.locator('#evidence-rows tr').first().evaluate(e=>[3,4,5,6].map(i=>getComputedStyle(e.children[i].querySelector('.admin-error-counter')||e.children[i].querySelector('a')||e.children[i]).fontSize));
    assert.equal(new Set(fonts).size,1,'Installation numbers share size');
    assert.equal(await page.locator('.installation-kpis .map-statistics-kpi-value').count(),5,'Installation summary has five operational metrics');
    assert.deepEqual(await page.locator('.installation-kpis .map-statistics-kpi-value').evaluateAll(es=>[...new Set(es.map(e=>getComputedStyle(e).borderTopWidth))]),['0px']);
    const danger=await page.locator('.installation-failed-value').evaluateAll(es=>es.map(e=>getComputedStyle(e).color));
    assert.equal(new Set(danger).size,1,'Failed summary and record numbers share danger color');
    assert.match(await page.locator('.page-meta').innerText(),/All time · Model evidence/);
    assert.equal(await page.locator('.installation-failed-value').first().innerText(),'10','Model evidence keeps ten failed results');
   }
   if(name==='device'){
    assert.equal(await page.locator('.attempts-metric>span').evaluate(e=>getComputedStyle(e,'::after').content),'none');
    assert.equal(await page.locator('.map-statistics-kpi-secondary').evaluate(e=>getComputedStyle(e).borderTopWidth),'1px');
    const metrics=await page.locator('.model-statistics').boundingBox(), alert=await page.locator('.model-review-alert').boundingBox();
    if(metrics&&alert) assert(alert.y-(metrics.y+metrics.height)>=16,'Device summary and alert keep a section gap');
    const columns=await page.locator('.model-evidence-grid').evaluate(e=>getComputedStyle(e).gridTemplateColumns);
    assert.equal(await page.locator('.model-evidence-summary>.model-administration').count(),1,'Administration stays in the left evidence column');
    assert.equal(await page.locator('.model-evidence-summary>.device-overview-sections').count(),1,'Device and technical information stay in the left evidence column');
    if(width>900){assert.equal(columns.split(' ').length,2,'Device summary and history share a desktop row');assert.equal(await page.locator('.model-evidence-history .model-history-table').evaluate(e=>getComputedStyle(e).display),'block','Device history reuses record layout');}
    else {assert.equal(columns.split(' ').length,1,'Device evidence stacks narrow');const left=await page.locator('.model-evidence-summary').boundingBox(),history=await page.locator('.model-evidence-history').boundingBox();assert(history.y>=left.y+left.height,'Device history follows left-column content when stacked');}
   }
   if(name==='statistics'){
    assert.match(await page.locator('#map-statistics-world-map-status').innerText(),/\d+ countries? · \d+ installs/,'World map reports mapped successful installs');
    assert.equal(await page.locator('#map-statistics-updates').isVisible(),true,'Updates stays visible at zero or nonzero');
    const mapTrendCharts=page.locator('.map-statistics-page .overview-trend-chart:visible');
    assert.equal(await mapTrendCharts.count(),2,'Maps keeps separate download and install trends');
    for(const chart of await mapTrendCharts.all()){
     const ticks=await chart.locator('.overview-chart-grid').evaluateAll(lines=>lines.map(line=>Number(line.getAttribute('y1'))));
     assert.equal(ticks.length,5,'Maps trend has five grid bands');
     assert.equal(new Set(ticks.slice(1).map((value,index)=>Math.round((ticks[index]-value)*10)/10)).size,1,'Maps grid bands are evenly spaced');
    }
    const coverage=await page.locator('.map-statistics-coverage-layout').boundingBox(), providers=await page.locator('#map-statistics-provider-table').boundingBox();
    if(coverage&&providers) assert(providers.y>=coverage.y+coverage.height,'Provider comparison does not overlap coverage');
    assert.equal(await page.getByText('Diagnostic coverage',{exact:true}).count(),0,'Non-actionable diagnostic coverage is removed');
    assert.equal(await page.locator('#map-rows tr').count(),10,'Top countries shows up to ten ranked countries');
    assert.equal(await page.locator("[data-stat='failedInstalls']").innerText(),'10','Maps excludes non-canonical fresh failures');
    assert.match(await page.locator('.map-statistics-trends').innerText(),/Week of/,'Current one-month fixture uses weekly buckets');
    if(width>760){const date=page.locator('#provider-statistic-rows td.column-date').first();assert.equal(await date.evaluate(e=>getComputedStyle(e).whiteSpace),'nowrap','Last install stays one line');}
   }
   if(name.startsWith('identification')){
    assert.equal(await page.locator('h1').innerText(),'Model source review');
    assert(!/Review required/.test(await page.locator('main').innerText()));
    assert.equal(await page.getByText('Model codes',{exact:true}).count(),0);
    assert.equal(await page.getByText('Review guidance',{exact:true}).count(),0);
    assert.equal(await page.locator('.identification-result-count').count(),0);
    assert.deepEqual(await page.locator('.identity-mapping-source').first().locator('h3').allTextContents(),['Source reported','Match to',...(name==='identification-ambiguous'?['Other models using this code']:[]),'Confirm match']);
    assert.equal(await page.getByRole('button',{name:'Approve match'}).first().isVisible(),true);
    assert.equal(await page.getByRole('button',{name:'Reject match'}).first().isVisible(),true);
    const approve=page.getByRole('button',{name:'Approve match'}).first(), reject=page.getByRole('button',{name:'Reject match'}).first();
    assert.notEqual(await approve.evaluate(e=>getComputedStyle(e).backgroundColor),await reject.evaluate(e=>getComputedStyle(e).backgroundColor),'Approve and reject remain visually distinct');
    assert.equal(await page.locator('.identification-technical').count(),1);
    assert.equal(await page.locator('.identification-technical').getAttribute('open'),null);
    assert.equal(await page.getByText('006-B4953-00',{exact:true}).isVisible(),false,'Raw product code stays behind Technical details');
    const action=await page.locator('.identification-confirm').first().boundingBox();
    assert(action&&action.y<1000,'Primary match action appears in the first practical viewport');
    if(width<=760){const [heading,target]=await page.locator('.identification-match>*').evaluateAll(es=>es.slice(0,2).map(e=>Math.round(e.getBoundingClientRect().x)));assert(Math.abs(heading-target)<=1,'Match target shares the narrow-layout left edge');}
    if(name==='identification-ambiguous')assert.equal(await page.locator('.identification-other-models li').count(),2);
    if(name==='identification-no-others'||name==='identification')assert.equal(await page.locator('.identification-other-models').count(),0);
    if(name==='identification-decided')assert.match(await page.locator('.identification-existing-decision').innerText(),/Current decision: Approved/);
   }
   if(name==='diagnostics'){
    const inspect=page.getByRole('button',{name:/Inspect installation/}).first();
    if(await inspect.count()){
     await inspect.click(); const dialog=page.locator('dialog[open]').first();
     assert.equal(await dialog.count(),1,'Diagnostic opens');
     if(width>800){
      const bottoms=await dialog.locator('.diagnostic-actions-grid>form.diagnostic-action-form').evaluateAll(forms=>forms.slice(0,2).map(form=>{const button=form.querySelector('button[type="submit"]');return button?Math.round(button.getBoundingClientRect().bottom):null;}));
      if(bottoms.length===2&&bottoms.every(value=>value!==null))assert(Math.abs(bottoms[0]-bottoms[1])<=1,'Diagnostic action buttons align');
      const secondary=await dialog.locator('.diagnostic-secondary-disclosure').evaluateAll(es=>es.map(e=>({width:Math.round(e.getBoundingClientRect().width),background:getComputedStyle(e).backgroundColor,borderRadius:getComputedStyle(e).borderRadius,padding:getComputedStyle(e).padding})));
      assert.equal(secondary.length,2);assert.equal(secondary[0].width,secondary[1].width);assert.equal(secondary[0].background,secondary[1].background);assert.equal(secondary[0].borderRadius,secondary[1].borderRadius);assert.equal(secondary[0].padding,secondary[1].padding);
     }
     await dialog.locator('.dialog-close').click();
    }
   }
   if(['installations','device','statistics'].includes(name)){
    const selector=name==='statistics'?'.map-statistics-kpi-value:not(.failed)>strong':'.admin-kpi-panel .map-statistics-kpi-value:not(.failed):not(.timestamp-metric)>strong';
    assert.equal(await page.locator(selector).first().evaluate(e=>getComputedStyle(e).fontSize),'24px',`${name}: shared KPI size`);
   }

   await page.screenshot({path:`${output}/${name}-${width}.png`,fullPage:true});
  }
  await page.goto(base+'/admin/device-empty.html');
  const empty=page.locator('.model-evidence-history .compact-empty-state');
  assert.equal(await empty.count(),1,'Device history uses one compact empty state');
  assert.equal(await empty.locator('p.empty').innerText(),'No installation history for this device.');
  assert.equal(await page.locator('.model-evidence-history table, .model-evidence-history .pagination').count(),0,'Empty device history has no table or pagination chrome');
  for(const label of ['Administration','Device information','Technical details']){
   const summary=page.getByText(label,{exact:true}).filter({hasNot:page.locator('h1')}).first();
   const wasOpen=await summary.evaluate(e=>e.parentElement.open);
   await summary.focus(); await page.keyboard.press('Space');
   assert.equal(await summary.evaluate(e=>e.parentElement.open),!wasOpen,label+' toggles from the keyboard');
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
 assert.match(names[0],/fēnix 1 /); assert.match(names[1],/fēnix 2 /); assert.equal(names.length,25);
 assert.equal(await page.locator('#installation-pagination').isVisible(),true);
 await page.locator('[data-installation-page="next"]').click();
 assert.match(await page.locator('#installation-pagination').innerText(),/page 2 of 5/);
 assert.equal(await page.locator('#evidence-rows tr:not([hidden])').count(),25);
 await page.locator('[data-installation-sort="lastSuccess"]').click();
 let dates=await page.locator('#evidence-rows tr:not([hidden])').evaluateAll(es=>es.map(e=>e.dataset.lastSuccess));
 assert.equal(dates.length,25);
 await page.locator('[data-installation-sort="lastSuccess"]').click();
 dates=await page.locator('#evidence-rows tr:not([hidden])').evaluateAll(es=>es.map(e=>e.dataset.lastSuccess));assert.equal(dates.length,25);
 await page.locator('#evidence-search').fill('fēnix 12 Very');assert.equal(await page.locator('#evidence-rows tr:not([hidden])').count(),1);
 assert.equal(await page.locator('#installation-pagination').isVisible(),false);
 assert.equal(await page.locator('[data-filter-clear]').isVisible(),true);
 assert.match(page.url(),/search=/);await page.reload();assert.equal(await page.locator('#evidence-search').inputValue(),'fēnix 12 Very');
 await page.locator('#evidence-search').fill('No matching model');
 assert.equal(await page.locator('#installation-empty').innerText(),'No matching models.');
 assert.equal(await page.locator('#installation-table').isVisible(),false);
 assert.equal(await page.locator('[data-filter-clear]').isVisible(),true);
 await page.goto(base+'/admin/health.html');await page.locator('#health-status').selectOption('FAILED');
 assert.equal(await page.locator('[data-health-status]:not([hidden])').count(),5);
 await page.locator('#health-search').fill('Check 2');assert.equal(await page.locator('[data-health-status]:not([hidden])').count(),1);
 const healthTechnical=page.locator('[data-health-status]:not([hidden]) details').first();
 await healthTechnical.locator('summary').focus();await page.keyboard.press('Enter');
 assert.equal(await healthTechnical.getAttribute('open'),'');
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
 await refresh.locator('form[method="post"] textarea').first().evaluate(e=>e.closest('details').open=true);
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
 console.log('PASS: 48 responsive pages at 1440/1024/720/390, model-source flows, owner fixes, sorting all 120 identities, persisted filters, disclosure geometry, polling and error handling.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
