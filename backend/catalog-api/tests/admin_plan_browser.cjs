/* Browser acceptance on local fixture server only. Usage: [ADMIN_BROWSER_ONLY=dropdowns] node file playwrightModule chromePath baseURL outputDir */
const assert=require('node:assert/strict');
const {chromium}=require(process.argv[2]);
// Owner spacing rule (admin-behavior-contract.md): separate cards keep 24px (16px at <=700px); a filter bar keeps 12px above its own table; rows inside one table are not cards.
const tightCardGaps=(page,width)=>page.evaluate(cardGap=>{
 const isCard=e=>{if(e.matches('select,input,textarea,button,.admin-dropdown,.admin-dropdown *'))return false;const s=getComputedStyle(e),r=e.getBoundingClientRect();return parseFloat(s.borderTopWidth)>0&&parseFloat(s.borderBottomWidth)>0&&s.borderTopStyle!=='none'&&s.borderBottomStyle!=='none'&&!/^(transparent|rgba\(.*,\s*0\))$/.test(s.backgroundColor)&&r.height>40&&r.width>200;};
 const cards=[];const walk=el=>{for(const c of el.children){const s=getComputedStyle(c);if(s.display==='none'||s.visibility==='hidden')continue;if(isCard(c))cards.push({e:c,r:c.getBoundingClientRect()});else walk(c);}};
 const main=document.querySelector('main');if(main)walk(main);
 const overlap=(a,b)=>Math.min(a.r.right,b.r.right)-Math.max(a.r.left,b.r.left)>=100;
 const label=e=>e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(e.classList.length?'.'+[...e.classList].slice(0,2).join('.'):'');
 const tight=[];
 for(const a of cards){
  const below=cards.filter(b=>b!==a&&overlap(a,b)&&b.r.top>=a.r.bottom-1).sort((x,y)=>x.r.top-y.r.top);const b=below[0];
  if(!b||cards.some(c=>c!==a&&c!==b&&overlap(a,c)&&c.r.top>=a.r.bottom-1&&c.r.bottom<=b.r.top+1))continue;
  const table=a.e.closest('table');if(table&&table===b.e.closest('table'))continue;
  const minimum=a.e.matches('.filter-bar')&&(b.e.matches('.table-wrap')||b.e.closest('table'))?12:cardGap;
  const gap=b.r.top-a.r.bottom;if(gap<minimum-0.5)tight.push(`${label(a.e)} -> ${label(b.e)}: ${Math.round(gap)}px < ${minimum}px`);
 }
 return tight;
},width<=700?16:24);
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[3],headless:true});
 try {
 const page=await browser.newPage(); const base=process.argv[4], output=process.argv[5];
 const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
 // ADMIN_BROWSER_ONLY=dropdowns runs only the filter dropdown block below.
 const onlyDropdowns=process.env.ADMIN_BROWSER_ONLY==='dropdowns';
 if(!onlyDropdowns) for(const width of [1440,1024,720,390]){
  await page.setViewportSize({width,height:1000});
  for(const name of ['overview','installations','providers','provider','statistics','device','health','diagnostics','identification','identification-ambiguous','identification-decided','identification-no-others','identity-review','identity-review-empty','diagnostics-identity']){
   await page.goto(base+'/admin/'+name+'.html');await page.waitForTimeout(150);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${name}/${width}: page overflow`);
   assert.deepEqual(errors.splice(0),[],`${name}/${width}: script errors`);
   assert(!/\bFresh\b/i.test(await page.locator('main').innerText()), `${name}: no Fresh labels`);
   assert.equal(await page.locator('.admin-glossary-link').count(),0,`${name}: no glossary ? links`);
   const unsortable=await page.evaluate(()=>[...document.querySelectorAll('main table')].filter(t=>t.tHead&&t.getAttribute('role')!=='presentation').flatMap(t=>{const style=getComputedStyle(t.tHead);if(style.clip.startsWith('rect(0')||(style.position==='absolute'&&parseFloat(style.height)<=1))return [];const row=t.tHead.rows[t.tHead.rows.length-1];return [...row.cells].filter(th=>th.textContent.trim()&&th.colSpan===1&&!th.querySelector('button')).map(th=>th.textContent.trim());}));
   assert.deepEqual(unsortable,[],`${name}: every visible data-table header sorts`);
   assert.deepEqual(await tightCardGaps(page,width),[],`${name}/${width}: separate cards keep the shared card gap`);
   if(name==='health'){
    const indexnow=page.locator("[data-health-name*='indexnow']");
    assert.equal(await indexnow.count(),1,'one IndexNow card');
    const indexnowSummary=indexnow.locator('.system-health-issue-heading');
    assert.equal(await indexnowSummary.locator('h2').innerText(),'Search indexing');
    assert.equal(await indexnowSummary.locator('.admin-pill').count(),1,'IndexNow summary has one health pill');
    assert.equal(await indexnowSummary.locator('.health-issue').count(),0,'IndexNow summary has no result detail');
    assert(!/Last check|Pending URLs|Validation pending/i.test(await indexnowSummary.innerText()),'IndexNow summary has no expanded details');
    const indexnowTechnical=indexnow.locator('details.system-health-technical');
    await indexnowTechnical.locator('summary').click();
    assert.match(await indexnow.locator('.disclosure-body').innerText(),/validation message remains readable/);
    assert.match(await indexnow.locator('.disclosure-body').innerText(),/https:\/\/terento\.app\/guides\/install-garmin-maps-mac\//);
    assert.equal(await page.locator('[data-health-name]').first().locator('.system-health-cause').count(),1,'other health card keeps its summary issue');
   }
   if(name==='overview'){
    assert.equal(await page.locator('.overview-tiles, .overview-page>.admin-metric-row').count(),0,'Dashboard has no summary tile row');
    const totals=await page.locator('.overview-card-totals').evaluateAll(es=>es.map(e=>({card:e.closest('section').id,icons:e.querySelectorAll('.admin-icon').length,values:[...e.querySelectorAll('strong')].map(s=>getComputedStyle(s).fontSize)})));
    assert.deepEqual(totals.map(t=>t.card),['overview-download-trend','overview-trend','overview-attention'],'Downloads, Installs and Needs attention headers carry the totals');
    assert(totals.every(t=>t.icons===0),'Header totals carry no icons');
    assert.equal(new Set(totals.flatMap(t=>t.values)).size,1,'Header totals share one numeric size');
    if(width>900){const heads=await page.locator('#overview-download-trend .admin-card-head, #overview-trend .admin-card-head, #overview-attention .admin-card-head, #overview-activity .admin-card-head').evaluateAll(es=>es.map(e=>Math.round(e.getBoundingClientRect().height)));assert(heads[0]===heads[1]&&heads[2]===heads[3],'Card headers in a row share one height');}
    assert.equal(await page.locator('.overview-download-panel').count(),1,'App downloads chart remains visible');
    assert.equal(await page.locator('.overview-download-panel h2').innerText(),'App downloads');
    assert.deepEqual(await page.locator('main>.overview-primary-grid, main>.overview-composition-grid').evaluateAll(es=>es.map(e=>e.className)),['overview-primary-grid','overview-composition-grid']);
    assert.equal(await page.locator('.overview-primary-grid .admin-card-head .admin-scope-chip').count(),2,'Each chart header shows its period scope');
    assert.equal(await page.locator('.overview-primary-grid .overview-all-time, .overview-primary-grid .overview-purposes, .overview-primary-grid .admin-legend strong').count(),0,'Chart cards show only header totals, chart and a count-free legend');
    assert.equal(await page.locator('.overview-attention-row').count(),await page.locator('.overview-attention-row strong').evaluateAll(es=>es.filter(e=>e.textContent.trim()!=='0').length),'Needs attention lists only rows with work');
    assert(await page.locator('.overview-attention-row').count()>0,'Fixture has open work');
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
    if(width>900){assert(Math.abs(charts[0].y-charts[1].y)<=1,'Dashboard charts share a row');assert(Math.abs(attention.y-activity.y)<=1,'Attention and Activity share a row');const funnel=await page.locator('.overview-funnel-panel').evaluate(e=>e.getBoundingClientRect());assert(app.y>=attention.y+attention.height+15,'App downloads follows the Needs attention row');assert(Math.abs(app.y-funnel.y)<=1&&Math.abs(app.height-funnel.height)<=1,'First run and App downloads share one row at one height');assert(Math.abs(app.x-activity.x)<=1&&Math.abs(app.width-activity.width)<=1,'Right-column cards align');assert(Math.abs(attention.height-activity.height)<=1&&Math.abs(charts[0].height-charts[1].height)<=1,'Cards in a row share one height');assert(Math.abs(activity.width-attention.width)<=1,'Dashboard composition columns match');assert(app.width<width*.6,'App downloads occupies half row');}
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
    assert.equal(await page.locator('.installation-kpis .admin-metric').count(),5,'Installation summary has five operational metrics');
    assert.deepEqual(await page.locator('.installation-kpis .admin-metric').evaluateAll(es=>[...new Set(es.map(e=>getComputedStyle(e).borderTopWidth))]),['0px']);
    assert.equal(await page.locator('.installation-kpis .admin-scope-chip').count(),0,'Installation tiles carry no scope chips (owner decision 2026-10-06)');
    assert.match(await page.locator('.page-meta').innerText(),/All time · Model evidence/);
    assert.equal(await page.locator("[data-stat='failed']").first().innerText(),'10','Model evidence keeps ten failed results');
   }
   if(name==='device'){
    const summaryGaps=await page.locator('.model-evidence-summary').evaluate(e=>{const rects=[...e.children].filter(c=>getComputedStyle(c).display!=='none').map(c=>c.getBoundingClientRect());return rects.slice(1).map((r,i)=>Math.round(r.top-rects[i].bottom));});
    assert(summaryGaps.length>=2,'Device summary column stacks several cards');
    assert.deepEqual([...new Set(summaryGaps)],[width<=700?16:24],`device/${width}: summary column cards share one card gap`);
    assert.equal(await page.locator('section[aria-labelledby="model-installation-kpis-title"] .admin-metric').count(),5,'Installs card has five tiles');
    const metrics=await page.locator('.model-statistics:not(.model-update-statistics)').boundingBox(), alert=await page.locator('.model-review-alert').boundingBox();
    if(metrics&&alert) assert(alert.y-(metrics.y+metrics.height)>=16,'Device summary and alert keep a section gap');
    const columns=await page.locator('.model-evidence-grid').evaluate(e=>getComputedStyle(e).gridTemplateColumns);
    assert.equal(await page.locator('.model-evidence-summary>.model-administration').count(),1,'Administration stays in the left evidence column');
    assert.equal(await page.locator('.model-evidence-summary>.device-overview-sections').count(),1,'Device and technical information stay in the left evidence column');
    if(width>900){assert.equal(columns.split(' ').length,2,'Device summary and history share a desktop row');const historyTable=page.locator('.model-evidence-history .model-history-table');if(width>=1024){assert.equal(await historyTable.evaluate(e=>getComputedStyle(e).display),'table','Desktop history uses compact table rows');assert(await historyTable.evaluate(e=>e.scrollWidth<=e.parentElement.clientWidth+1),'Compact history fits its column');assert(await historyTable.locator('tbody tr').first().evaluate(e=>e.getBoundingClientRect().height<80),'History rows stay compact');assert.equal(await historyTable.locator('.diagnostic-review').count()>0,true,'Inspect actions remain');}else assert.equal(await historyTable.evaluate(e=>getComputedStyle(e).display),'block','Device history reuses record layout below 1024 px');}
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
    if(coverage&&providers) assert(providers.y>=coverage.y+coverage.height,'Providers does not overlap coverage');
    assert.equal(await page.getByText('Diagnostic coverage',{exact:true}).count(),0,'Non-actionable diagnostic coverage is removed');
    assert.equal(await page.locator('#map-rows tr').count(),10,'Top countries shows up to ten ranked countries');
    assert.equal(await page.locator("#map-statistics-metrics [data-stat='failedInstalls']").innerText(),'10','Maps excludes non-canonical fresh failures');
    assert.equal(await page.locator('main .admin-scope-chip').count(),0,'Maps carries no scope chips; the filter bar names the period (owner decision 2026-10-06)');
    assert.equal(await page.locator('.map-statistics-trends .admin-card-head .overview-card-totals').count()===2,true,'Maps chart cards show period totals like the Dashboard');
    assert.equal(await page.locator('#map-rows tr:not([hidden])').count()>=Math.min(10,await page.locator('#map-rows tr').count()),true,'Top countries shows at least ten countries');
    assert.equal(await page.locator('[data-provider-stream]').count(),3,'Providers switches one stream at a time');
    if(width>760){const date=page.locator('#provider-statistic-rows td.column-date').first();assert.equal(await date.evaluate(e=>getComputedStyle(e).whiteSpace),'nowrap','Last install stays one line');}
   }
   if(name.startsWith('identification')){
    assert.equal(await page.locator('h1').innerText(),'Model sources');
    assert(!/Review required/.test(await page.locator('main').innerText()));
    assert.equal(await page.getByText('Model codes',{exact:true}).count(),0);
    assert.equal(await page.getByText('Review guidance',{exact:true}).count(),0);
    assert.equal(await page.locator('.identification-result-count').count(),0);
    assert.deepEqual(await page.locator('.identity-mapping-source').first().locator('h3').allTextContents(),['Source says','Catalog model',...(name==='identification-ambiguous'?['Same code']:[]),'Confirm']);
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
      const shape=await dialog.evaluate(d=>{const inner=d.querySelector('.diagnostic-detail-inner');const details=[...d.querySelectorAll('details')];return {last:inner.lastElementChild.className,classes:details.map(e=>e.className),boxes:[...new Set(details.map(e=>{const c=getComputedStyle(e);return [c.borderTopWidth,c.borderRadius,c.backgroundColor].join('|');}))],summaries:[...new Set(details.map(e=>{const c=getComputedStyle(e.querySelector('summary'));return [c.fontFamily,c.fontSize,c.fontWeight,c.color].join('|');}))],incomplete:inner.textContent.includes('Identity incomplete')};});
      assert.match(shape.last,/diagnostic-identity-section/,'Device identity is the last dialog section');
      assert(shape.classes.every(c=>c.startsWith('admin-disclosure diagnostic-disclosure')),'One disclosure class in the dialog');
      assert.equal(shape.boxes.length,1,'One disclosure box style');assert.equal(shape.summaries.length,1,'One disclosure summary style');
      assert.equal(shape.incomplete,false,'No separate identity-incomplete notice');
     }
     await dialog.locator('.dialog-close').click();
    }
   }
   if(name==='identity-review'){
    assert.equal(await page.locator('h1').innerText(),'Identity review');
    assert.equal(await page.locator('[data-identity-review-item]').count(),6,'Every pending installation is one item');
    assert.equal(await page.locator('[data-identity-review-group]').count(),4,'Items group by reported identity');
    assert.equal(await page.locator('main .diagnostic-review, main dialog').count(),0,'No Inspect step in the queue');
    assert.equal(await page.locator('[data-identity-review-item] .identity-review-details').count(),6,'Each item keeps a Details link');
    assert.equal(await page.locator('[data-identity-form][data-identity-inline] .identity-picker:visible').count(),0,'Pickers stay closed until Edit / Pick model');
    if(width>=900){const [facts,decision]=await page.locator('[data-identity-review-item]').first().evaluate(e=>[...e.children].map(c=>c.getBoundingClientRect()));assert(decision.x>facts.x+facts.width-1&&Math.abs(decision.y-facts.y)<=2,'Facts and the identity decision share one row');}
   }
   if(name==='identity-review-empty'){
    assert.equal(await page.locator('main').getByText('No installations wait for identity review.',{exact:true}).isVisible(),true,'Empty queue says so');
   }
   if(name==='diagnostics-identity'){
    assert.equal(await page.locator('main .admin-scope-chip').count(),0,'No All time / Now chips under the numbers');
    assert.equal(await page.locator('#diagnostic-filters select').count(),0,'Quick filters, not a select');
    assert.equal(await page.locator('#diagnostic-filters [data-history-filter]').count(),7);
    assert.equal(await page.locator('#diagnostic-results-count').innerText(),'','No N records line');
    const pill=await page.locator("[data-stat='evidence'] .admin-pill").evaluate(e=>({w:e.getBoundingClientRect().width,h:e.getBoundingClientRect().height,tile:e.closest('.admin-metric').getBoundingClientRect().width}));
    assert(pill.h<=30&&pill.w<pill.tile*0.8,'Evidence is a normal status pill, not stretched');
    assert.equal(await page.getByRole('link',{name:/Review all pending identities/}).count(),1);
    await page.locator("[data-history-filter='identity-pending']").click();
    assert.equal(await page.locator('#diagnostic-rows tr:not([hidden])').count(),await page.locator("#diagnostic-rows tr[data-identity-pending='true']").count(),'Identity review quick filter');
    await page.locator("[data-history-filter='succeeded']").click();
    assert.equal(await page.locator('#diagnostic-rows tr:not([hidden])').count(),2,'Successful quick filter');
    assert.equal(await page.locator("[data-history-filter='succeeded']").getAttribute('aria-pressed'),'true');
    await page.locator("[data-history-filter='all']").click();
   }
   if(['installations','device','statistics'].includes(name)&&!(name==='statistics'&&width<=600)){
    const selector=name==='statistics'?'.map-statistics-metrics .admin-metric-value':name==='installations'?'.installation-kpis .admin-metric-value':'.admin-kpi-panel .admin-metric:not([data-kind]) .admin-metric-value';
    assert.equal(await page.locator(selector).first().evaluate(e=>getComputedStyle(e).fontSize),'24px',`${name}: shared KPI size`);
   }

   await page.screenshot({path:`${output}/${name}-${width}.png`,fullPage:true});
  }
  for(const name of ['devices','support-reports','support-report','missing-reports','glossary']){
   await page.goto(base+'/admin/'+name+'.html');await page.waitForTimeout(150);
   assert.deepEqual(errors.splice(0),[],`${name}/${width}: script errors`);
   assert.deepEqual(await tightCardGaps(page,width),[],`${name}/${width}: separate cards keep the shared card gap`);
  }
  await page.goto(base+'/admin/device-empty.html');
  const empty=page.locator('.model-evidence-history .compact-empty-state');
  assert.equal(await empty.count(),2,'Installation and Update history each use one compact empty state');
  assert.deepEqual(await empty.locator('p.empty').allInnerTexts(),['No installation history for this device.','No update history for this device.']);
  assert.equal(await page.locator('.model-evidence-history table, .model-evidence-history .pagination').count(),0,'Empty device history has no table or pagination chrome');
  for(const label of ['Administration','Device information','Technical details']){
   const summary=page.getByText(label,{exact:true}).filter({hasNot:page.locator('h1')}).first();
   const wasOpen=await summary.evaluate(e=>e.parentElement.open);
   await summary.focus(); await page.keyboard.press('Space');
   assert.equal(await summary.evaluate(e=>e.parentElement.open),!wasOpen,label+' toggles from the keyboard');
   assert.equal(await summary.evaluate(e=>Math.round(e.getBoundingClientRect().height)),44,label+' shared height');
  }
 }
 // Filter dropdowns (owner decision 2026-10-06): every Admin filter select opens one styled
 // listbox directly below its field (above only without room), never covering it, with the
 // native select kept as the source of truth. POST-form selects and the time zone stay native.
 {
  const fs=require('node:fs'), path=require('node:path');
  const dropdown=await browser.newPage();
  const logo=fs.readFileSync(path.join(__dirname,'../../../brand/logo/logo.svg'));
  await dropdown.route('https://terento.app/**',route=>route.fulfill({status:200,contentType:'image/svg+xml',body:logo}));
  const dropdownErrors=[];dropdown.on('pageerror',e=>dropdownErrors.push(e.message));
  const expected={overview:['overview-period'],installations:['evidence-status','evidence-sort'],devices:['device-family','device-support','device-status','device-mobile-sort'],statistics:['map-statistics-provider','map-statistics-event','map-statistics-outcome'],providers:[],provider:['provider-package-page-size'],health:[],diagnostics:[],'support-reports':[],device:['diagnostic-state-filter']};
  const navigates=new Set(['overview-period','map-statistics-range','map-statistics-provider']);
  const exercised=new Set();
  const settle=async name=>{if(name==='overview')await dropdown.waitForURL(/timeZone=/);await dropdown.waitForTimeout(50);};
  const control=id=>dropdown.locator(`#${id}`).locator('xpath=following-sibling::button[contains(@class,"admin-dropdown-button")]');
  const geometry=id=>dropdown.evaluate(id=>{const select=document.getElementById(id),button=select.parentElement.querySelector('.admin-dropdown-button'),list=document.getElementById(button.getAttribute('aria-controls'));const b=button.getBoundingClientRect(),l=list.getBoundingClientRect(),option=list.querySelector('[role="option"][aria-selected="true"]')||list.querySelector('[role="option"]');return {viewport:innerHeight,hidden:list.hidden,expanded:button.getAttribute('aria-expanded'),buttonTop:b.top,buttonBottom:b.bottom,buttonLeft:b.left,buttonWidth:b.width,listTop:l.top,listBottom:l.bottom,listLeft:l.left,listWidth:l.width,background:getComputedStyle(list).backgroundColor,border:getComputedStyle(list).borderTopWidth,optionFont:option&&getComputedStyle(option).fontFamily,optionSize:option&&getComputedStyle(option).fontSize,buttonSize:getComputedStyle(button).fontSize,selectedCheck:option&&getComputedStyle(option.querySelector('.admin-dropdown-check')).visibility,focused:document.activeElement===button,value:select.value,text:button.textContent.trim(),selectedLabel:select.selectedOptions[0]?.label,active:button.getAttribute('aria-activedescendant')};},id);
  const reveal=id=>dropdown.evaluate(id=>{const select=document.getElementById(id);for(let node=select;node;node=node.parentElement){if(node.tagName==='DETAILS')node.open=true;if(node.tagName==='FORM'&&node.hidden)node.hidden=false;}const extra=select.closest('.mobile-filter-options');if(extra&&extra.hidden)document.querySelector(`[aria-controls="${extra.id}"]`)?.click();select.parentElement.scrollIntoView({block:'center'});},id);
  for(const width of [1440,390]){
   await dropdown.setViewportSize({width,height:1000});
   for(const [name,ids] of Object.entries(expected)){
    await dropdown.goto(base+'/admin/'+name+'.html');await settle(name);
    const inventory=await dropdown.evaluate(()=>({marked:[...document.querySelectorAll('select[data-admin-dropdown]')].map(s=>s.id),enhanced:[...document.querySelectorAll('select[data-admin-dropdown]')].filter(s=>s.parentElement.matches('.admin-dropdown')&&s.tabIndex===-1&&s.getAttribute('aria-hidden')==='true'&&s.labels.length+(s.getAttribute('aria-label')?1:0)>0).length,native:[...document.querySelectorAll('form[method="post"] select, dialog select, #admin-timezone, #provider-health-interval')].filter(s=>s.closest('.admin-dropdown')).length,lists:document.querySelectorAll('.admin-dropdown-list').length}));
    assert.deepEqual(inventory.marked,ids,`${name}/${width}: filter selects use the shared dropdown`);
    assert.equal(inventory.enhanced,ids.length,`${name}/${width}: each native select stays labelled and hidden behind its button`);
    assert.equal(inventory.native,0,`${name}/${width}: POST-form, dialog and time-zone selects stay native`);
    assert.equal(inventory.lists,ids.length,`${name}/${width}: one listbox per dropdown`);
    for(const id of ids){
     await dropdown.goto(base+'/admin/'+name+'.html');await settle(name);
     await reveal(id);
     const button=control(id);
     if(!await button.isVisible())continue;
     exercised.add(`${name}:${id}`);
     const before=await geometry(id);
     assert.equal(before.text,before.selectedLabel,`${name}/${id}: button shows the selected option`);
     await button.click();
     let open=await geometry(id);
     assert.equal(open.hidden,false,`${name}/${id}: click opens the listbox`);
     assert.equal(open.expanded,'true');
     assert(open.listTop>=open.buttonBottom||open.listBottom<=open.buttonTop,`${name}/${width}/${id}: listbox never covers the field`);
     assert(open.listTop>=open.buttonBottom||open.viewport-open.buttonBottom<open.listBottom-open.listTop+12,`${name}/${width}/${id}: listbox opens below the field unless there is no room`);
     assert(Math.abs(open.listLeft-open.buttonLeft)<=1&&open.listWidth>=open.buttonWidth-1,`${name}/${id}: listbox is left-aligned and at least field width`);
     assert.equal(open.background,'rgb(255, 255, 255)',`${name}/${id}: listbox uses the white surface`);
     assert.equal(open.border,'1px');
     assert.match(open.optionFont,/^Inter\b/,`${name}/${id}: options use the UI font`);
     assert.equal(open.optionSize,open.buttonSize,`${name}/${id}: options match the field size`);
     assert.equal(open.selectedCheck,'visible',`${name}/${id}: selected option shows its check`);
     assert.equal(await dropdown.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${name}/${width}/${id}: open listbox causes no page overflow`);
     if(name==='installations'&&id==='evidence-status'||name==='overview'||name==='statistics'&&id==='map-statistics-provider')await dropdown.screenshot({path:`${output}/dropdown-${name}-${width}.png`});
     await dropdown.keyboard.press('Escape');
     open=await geometry(id);
     assert.equal(open.hidden,true,`${name}/${id}: Escape closes`);assert.equal(open.focused,true,`${name}/${id}: Escape returns focus`);
     await dropdown.keyboard.press('Alt+ArrowDown');
     open=await geometry(id);assert.equal(open.hidden,false,`${name}/${id}: Alt+ArrowDown opens`);
     assert.equal(open.active,`${(await button.getAttribute('aria-controls'))}-option-${await dropdown.evaluate(id=>document.getElementById(id).selectedIndex,id)}`,`${name}/${id}: the selected option starts active`);
     await dropdown.keyboard.press('Home');const home=(await geometry(id)).active;
     await dropdown.keyboard.press('ArrowDown');const next=(await geometry(id)).active;
     await dropdown.keyboard.press('End');const end=(await geometry(id)).active;
     assert(home!==next&&end!==home,`${name}/${id}: Home, ArrowDown and End move the active option`);
     await dropdown.keyboard.press('Escape');
     assert.equal((await geometry(id)).value,before.value,`${name}/${id}: Escape keeps the value`);
     await button.click();await dropdown.locator('main h1').click();
     assert.equal((await geometry(id)).hidden,true,`${name}/${id}: an outside click closes`);
     if(navigates.has(id))continue;
     await dropdown.evaluate(()=>{window.dropdownEvents=[];['input','change'].forEach(type=>document.addEventListener(type,event=>window.dropdownEvents.push(`${type}:${event.target.id}:${event.bubbles}`)));});
     const target=await dropdown.evaluate(id=>{const select=document.getElementById(id),last=select.options.length-1;return select.selectedIndex===last?{key:'Home',value:select.options[0].value,label:select.options[0].label}:{key:'End',value:select.options[last].value,label:select.options[last].label};},id);
     await button.focus();await dropdown.keyboard.press('Enter');await dropdown.keyboard.press(target.key);await dropdown.keyboard.press('Enter');
     const chosen=await geometry(id);
     assert.equal(chosen.hidden,true,`${name}/${id}: Enter selects and closes`);
     assert.equal(chosen.value,target.value,`${name}/${id}: keyboard choice sets select.value`);
     assert.equal(chosen.text,target.label,`${name}/${id}: button shows the new choice`);
     assert.deepEqual(await dropdown.evaluate(()=>window.dropdownEvents),[`input:${id}:true`,`change:${id}:true`],`${name}/${id}: real bubbling input and change events`);
     await dropdown.evaluate(([id,value])=>{document.getElementById(id).value=value;},[id,before.value]);
     assert.equal((await geometry(id)).text,before.text,`${name}/${id}: programmatic value changes stay in sync`);
    }
    // Pages keep reacting exactly as they did to the native select.
    if(name==='installations'){
     await dropdown.goto(base+'/admin/installations.html');await settle(name);await reveal('evidence-status');
     const rows=()=>dropdown.locator('#evidence-rows tr:not([hidden])').count();
     const all=await rows();assert(all>0);
     await control('evidence-status').click();await dropdown.getByRole('option',{name:'Testing',exact:true}).click();
     assert.equal(await dropdown.locator('#evidence-status').inputValue(),'testing');
     assert.equal(await rows(),0,'Evidence filter hides non-matching rows');
     await control('evidence-status').focus();await dropdown.keyboard.press('Enter');await dropdown.keyboard.type('v');
     assert.equal(await dropdown.locator('[role="option"].is-active').innerText(),'Verified','Type-ahead finds an option');
     await dropdown.keyboard.press('Enter');assert.equal(await rows(),all,'Choosing Verified restores the rows');
     await dropdown.evaluate(()=>{document.getElementById('evidence-status').disabled=true;});await dropdown.waitForTimeout(20);
     assert.equal(await control('evidence-status').isDisabled(),true,'Disabled select disables its dropdown');
     await dropdown.evaluate(()=>{document.getElementById('evidence-status').disabled=false;});
     if(width===1440){
      const field=await control('evidence-status').boundingBox();
      await dropdown.setViewportSize({width,height:Math.ceil(field.y+field.height+40)});await dropdown.evaluate(()=>scrollTo(0,0));
      await control('evidence-status').click();const flipped=await geometry('evidence-status');
      assert(flipped.listBottom<=flipped.buttonTop,'Without room below the listbox flips above and still does not cover the field');
      await dropdown.keyboard.press('Escape');await dropdown.setViewportSize({width,height:1000});
     }
    }
    if(name==='health'){
     await dropdown.locator("[data-quick-select='health-status'] [data-quick-value='FAILED']").click();
     assert.equal(await dropdown.locator('[data-health-status]:not([hidden])').count(),5,'Health status filter keeps working');
    }
    if(name==='overview'){
     await control('overview-period').click();await dropdown.getByRole('option',{name:'Last 7 days',exact:true}).click();
     await dropdown.waitForURL(/period=7d/);await dropdown.waitForFunction(()=>document.querySelector('#overview-period')?.dataset.adminDropdownReady==='true'&&document.querySelectorAll('.admin-dropdown-list').length===1);
     assert.equal(await control('overview-period').isVisible(),true,'Replaced Dashboard content gets a fresh dropdown');
    }
    if(name==='statistics'){
     await dropdown.goto(base+'/admin/statistics.html');await settle(name);
     await dropdown.locator("[data-quick-select='map-statistics-range'] [data-quick-value='7d']").click();
     await dropdown.waitForURL(/period=7d/);
    }
    assert.equal(await dropdown.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${name}/${width}: no page overflow`);
    assert.deepEqual(dropdownErrors.splice(0),[],`${name}/${width}: dropdown script errors`);
   }
  }
  for(const [name,ids] of Object.entries(expected))for(const id of ids)if(!/sort$/.test(id))assert(exercised.has(`${name}:${id}`),`${name}/${id}: dropdown was exercised`);
  assert(exercised.has('installations:evidence-sort')&&exercised.has('devices:device-mobile-sort'),'Mobile sort dropdowns were exercised');
  await dropdown.close();
  if(onlyDropdowns){console.log('PASS: filter dropdowns on 10 Admin pages at 1440/390 (placement, styling, keyboard, sync and page reactions).');return;}
 }
 await page.setViewportSize({width:1440,height:1000});
 // Identity review queue: Edit / pick / Confirm inline against a routed success; the page stays put.
 const posts=[];
 await page.route('**/admin/diagnostics/identity',route=>{posts.push(new URLSearchParams(route.request().postData()||''));return route.fulfill({status:200,contentType:'application/json',body:'{"saved":true}'});});
 await page.goto(base+'/admin/identity-review.html');
 const queueURL=page.url();
 const suggested=page.locator('[data-identity-review-item]').filter({hasText:'Forerunner 965'}).first();
 await suggested.getByRole('button',{name:'Confirm',exact:true}).click();
 await suggested.locator('.identity-review-confirmed').waitFor();
 assert.equal(page.url(),queueURL,'Confirm keeps the queue open');
 assert.match(await suggested.locator('.identity-review-confirmed').innerText(),/Confirmed\s+Forerunner 965/);
 assert.equal(await suggested.locator('.identity-review-confirmed a').getAttribute('href'),'/admin/devices/forerunner-965?from=installations#installations');
 let sent=posts.at(-1);assert.equal(sent.get('identity_action'),'ASSIGN');assert.equal(sent.get('canonical_device_model_id'),'forerunner-965');
 assert.equal(sent.get('return_to'),'/admin/review/identity');assert.match(sent.get('operation_key'),/^result:[0-9a-f-]{36}:0$/);assert.equal(sent.get('csrf_token'),'fixture');
 assert.equal(await page.locator('[data-identity-review-count]').innerText(),'5 installations','Remaining count updates');
 const ambiguous=page.locator('[data-identity-review-item]').first();
 const confirm=ambiguous.getByRole('button',{name:'Confirm',exact:true});
 assert.equal(await confirm.isDisabled(),true,'Confirm waits for a model');
 await ambiguous.getByRole('button',{name:'Pick model'}).click();
 assert.equal(await ambiguous.locator('[data-identity-device-id]').count(),2,'Pick model lists the two candidates');
 await ambiguous.locator("[data-identity-device-id='fenix-8-51-amoled']").click();
 assert.equal(await confirm.isDisabled(),false);
 assert.match(await ambiguous.locator('[data-identity-selection]').innerText(),/fēnix 8 · 51 mm/);
 await ambiguous.getByRole('button',{name:'Edit'}).click();
 await ambiguous.locator('[data-identity-search]').fill('47');
 await ambiguous.locator("[data-identity-device-id='fenix-8-47-amoled']").click();
 await confirm.focus();await page.keyboard.press('Enter');
 await ambiguous.locator('.identity-review-confirmed').waitFor();
 sent=posts.at(-1);assert.equal(sent.get('canonical_device_model_id'),'fenix-8-47-amoled','Edit changes the picked model');
 const catalog=page.locator('[data-identity-review-item]').filter({hasText:'Spain'});
 await catalog.getByRole('button',{name:'Pick model'}).click();
 assert.equal(await catalog.locator('[data-identity-device-id]').count(),4,'A whole-catalog pick clones the page catalog');
 await page.unroute('**/admin/diagnostics/identity');
 const detail=await page.locator('[data-identity-review-item]').nth(1).locator('.identity-review-details').getAttribute('href');
 assert.match(detail,/^\/admin\/diagnostics\?identity=.*identity_scope=unresolved#diagnostic-detail-[0-9a-f]{16}$/);
 await page.goto(base+'/admin/diagnostics-identity.html'+detail.slice(detail.indexOf('#')));
 assert.equal(await page.locator('dialog[open]').getAttribute('id'),detail.slice(detail.indexOf('#')+1),'Details opens that diagnostic');
 assert.deepEqual(errors.splice(0),[],'identity review: script errors');
 await page.goto(base+'/admin/installations-plan.html');
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
 await page.goto(base+'/admin/health.html');await page.locator("[data-quick-select='health-status'] [data-quick-value='FAILED']").click();
 assert.equal(await page.locator("[data-quick-value='FAILED']").getAttribute('aria-pressed'),'true');
 assert.equal(await page.locator('[data-health-status]:not([hidden])').count(),5);
 await page.locator('#health-search').fill('Check 2');assert.equal(await page.locator('[data-health-status]:not([hidden])').count(),1);
 const healthTechnical=page.locator('[data-health-status]:not([hidden]) details').first();
 await healthTechnical.locator('summary').focus();await page.keyboard.press('Enter');
 assert.equal(await healthTechnical.getAttribute('open'),'');
 // Polling is controlled without sleeping: the real installed handler runs against a routed snapshot.
 const refresh=await browser.newPage();await refresh.addInitScript(()=>{const original=setInterval;window.setInterval=(f,ms)=>ms===120000?(window.testPoll=f,1):original(f,ms);});
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
 const unsavedControl=refresh.locator('form[data-authorization-form] select[name="support_status"]');
 await unsavedControl.evaluate(e=>e.closest('details').open=true);
 await unsavedControl.selectOption('UNSUPPORTED');
 snapshot=JSON.stringify({...initial,device:'next'});await poll();
 let asked=false;refresh.once('dialog',async dialog=>{asked=true;await dialog.dismiss();});
 await notice.getByRole('button',{name:'Refresh'}).click();assert(asked);assert.equal(await unsavedControl.inputValue(),'UNSUPPORTED');
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
 console.log('PASS: 60 responsive pages, identity review inline confirm/pick/edit/details, at 1440/1024/720/390, model-source flows, owner fixes, sorting all 120 identities, persisted filters, disclosure geometry, polling and error handling.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
