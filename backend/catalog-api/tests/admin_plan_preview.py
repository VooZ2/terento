"""Build isolated Admin scale fixtures; never submits telemetry or admin actions."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from terento_catalog.admin import *
from terento_catalog.admin import _admin_device_payload, _system_health_card, _indexnow_card, _diagnostic_summary_by_identity, _map_statistics_summary


_HEALTH_KEYS=('website_status','catalog_status','redirect_status','download_status','mime_status','magic_status','zip_status','img_status','last_update_status')


def _provider_detail_fixture(summary):
    """A dense provider: package issues, long audit reasons, checks, runs, sources and preview layers."""
    regions=['Lithuania','Latvia','Estonia','Poland','Germany','Austria','Switzerland','Czechia','Slovakia','Hungary',
             'Slovenia','Croatia','Italy','France','Spain','Portugal','Belgium','Netherlands','Denmark','Norway',
             'Sweden','Finland','Iceland','Ireland','Romania','Bulgaria','Greece','Albania']
    broken={'Germany':'The download server returned HTTP 404 for this file.','Austria':'The download server returned HTTP 404 for this file.',
            'Italy':'The download server returned HTTP 404 for this file.','France':'The archive is not a valid ZIP file.',
            'Spain':'The download server returned HTTP 404 for this file.','Norway':'The download server returned HTTP 404 for this file.',
            'Greece':'The download server returned HTTP 404 for this file.'}
    maps=[]
    for index,region in enumerate(regions):
        slug=region.lower()
        failed=region in broken
        artifacts=[{'kind':'main','validation_status':'FAILED' if failed else 'VALIDATED','size_bytes':180_000_000+index,'install_size_bytes':240_000_000,
                    'source_url':f'https://download.freizeitkarte-osm.de/garmin/latest/freizeitkarte_{slug}.img.zip','source_updated_at':'2026-09-14',
                    'last_check':{'message':broken[region],'nextAction':'Recheck after the provider publishes a fixed file.','checkedAt':'2026-09-17T09:12:00Z'} if failed else {}}]
        if index%4==0:
            artifacts.append({'kind':'contours','validation_status':'VALIDATED','source_url':f'https://download.freizeitkarte-osm.de/garmin/latest/contours_{slug}.img.zip'})
        maps.append({'id':f'freizeitkarte-{slug}','name':region,'region':region,'release':'2026-09' if index%5 else '2026-08',
                     'availability':'UNAVAILABLE' if failed else 'AVAILABLE','artifact_count':len(artifacts),'broken_artifact_count':1 if failed else 0,
                     'artifacts':artifacts,'downloads_disabled':region=='Iceland','downloads_disabled_reason':'Provider asked us to pause this region.' if region=='Iceland' else None})
    download_sources=[{'source_type':'DOWNLOAD','source_url':a['source_url'],'enabled':True,'validation_status':a['validation_status'],'last_checked_at':'2026-09-17T09:12:00Z'}
                      for m in maps for a in m['artifacts']]
    original=[{'source_type':kind,'source_url':url,'enabled':True,'validation_status':'VALIDATED','last_checked_at':f'2026-09-1{7-i}T08:4{i}:00Z'}
              for i,(kind,url) in enumerate((('WEBSITE','https://www.freizeitkarte-osm.de/garmin/en/'),
                                            ('CATALOG','https://www.freizeitkarte-osm.de/garmin/en/downloads.html?catalog=europe&format=img&sort=region'),
                                            ('LICENSE','https://www.freizeitkarte-osm.de/garmin/en/licence.html'),
                                            ('CATALOG','https://download.freizeitkarte-osm.de/garmin/latest/manifest-europe-with-a-very-long-name.json')))]
    def check(day,hour,status='HEALTHY',**extra):
        record={'status':status,'checked_at':f'2026-09-{day:02d}T{hour:02d}:30:00Z','http_status':200,'duration_ms':125+day,'artifact_count':12,**{key:'HEALTHY' for key in _HEALTH_KEYS}}
        record.update(extra)
        return record
    health=[check(17,10),check(17,4),check(16,22,'DEGRADED',download_status='DEGRADED',error_detail='Two sampled downloads answered slower than 20 seconds.'),
            check(16,16),check(16,10),check(15,22,'DOWN',download_status='DOWN',http_status=503,error_detail='The download server answered 503 Service Unavailable.'),
            check(15,16),check(15,10)]
    runs=[{'id':40-i,'status':'FAILED' if i==3 else 'SUCCEEDED','started_at':f'2026-09-{17-i:02d}T10:10:00Z','finished_at':f'2026-09-{17-i:02d}T10:20:00Z',
           'package_count':28,'artifact_count':35,'new_package_count':0 if i else 1,'updated_package_count':200 if i==1 else 0,
           'release_change_detected':i==1,'latest_release':'2026-09','error_code':'catalog_timeout' if i==3 else None} for i in range(10)]
    many=[{'region':f'Region {n:03d}','packageId':f'freizeitkarte-r{n}','previousRelease':'2026-08','release':'2026-09'} for n in range(200)]
    audits=[
        {'action':'CATALOG_RELEASES_UPDATED','reason':'200 map releases changed during catalog collection','occurred_at':'2026-09-16T10:20:00Z','target':'freizeitkarte','details':{'packages':many}},
        {'action':'provider.previews_enabled','old_status':'ACTIVE','new_status':'ACTIVE','reason':'Map styles page needs comparison tiles.','occurred_at':'2026-09-15T18:02:00Z','admin_user_id':1},
        {'action':'package.downloads_disabled','reason':'Provider asked us to pause Iceland while they rebuild the contour layer; re-enable after their announcement.','occurred_at':'2026-09-15T12:44:00Z','admin_user_id':1,'target':'freizeitkarte-iceland'},
        {'action':'provider.health_schedule_changed','reason':'Every 6 hours','occurred_at':'2026-09-14T09:00:00Z','admin_user_id':1},
        {'action':'provider.status_changed','old_status':'PAUSED','new_status':'ACTIVE','reason':'Download server is back.','occurred_at':'2026-09-13T08:15:00Z','admin_user_id':1},
        {'action':'provider.status_changed','old_status':'ACTIVE','new_status':'PAUSED','reason':'Download server returns 503 for every region.','occurred_at':'2026-09-12T21:40:00Z','admin_user_id':1},
        {'action':'CATALOG_RELEASES_UPDATED','reason':'6 map releases changed during catalog collection','occurred_at':'2026-09-10T10:20:00Z','details':{'packages':many[:6]}},
        {'action':'provider.catalog_collected','reason':None,'occurred_at':'2026-09-09T10:20:00Z'},
        {'action':'provider.health_checked','reason':None,'occurred_at':'2026-09-08T10:20:00Z'},
        {'action':'package.downloads_enabled','reason':'Fixed upstream.','occurred_at':'2026-09-07T10:20:00Z','target':'freizeitkarte-latvia'},
    ]
    styles=('freizeitkarte','opentopomap','outdoor')
    layers=[{'area_id':f'alps-{n}','style_id':styles[n%3],'status':('AVAILABLE','AVAILABLE','PENDING','FAILED','NOT_COVERED')[n%5],
             'package_id':f'freizeitkarte-{regions[n].lower()}','package_version':'2026-09','rendered_at':'2026-09-16T02:10:00Z' if n%5<2 else None,
             'error_code':'render_timeout' if n%5==3 else None,'error_message':'Rendering stopped after 120 seconds.' if n%5==3 else None} for n in range(14)]
    detail=dict(summary,maps=maps,sources=original+download_sources,healthStatus='HEALTHY',healthHistory=health,activationGate={'canActivate':True},
                affectedPackageCount=len(broken),adapterId='freizeitkarte',website='https://www.freizeitkarte-osm.de/garmin/en/',
                license='ODbL 1.0 (map data) · CC BY-SA 4.0 (styles)',attribution='© OpenStreetMap contributors · Freizeitkarte',
                licenseUrl='https://www.freizeitkarte-osm.de/garmin/en/licence.html',
                monitoring={'intervalHours':6,'nextCheckAt':'2026-09-17T16:30:00Z','stale':False},
                previews={'enabled':True,'layers':layers})
    return detail,runs,audits


def build(root):
    root=Path(root); user={'username':'Preview', 'admin_review_summary':{'available':True,'installationIssues':20,'githubIssuesInProgress':5,'identityPending':12,'readyToPublish':3,'missingDiagnostics':8,'total':48}}
    rows=[{'model':f'fēnix {i+1} Very Long Authentic Model Name', 'compatibility_identity':f'model-{i}', 'canonical_device_model_id':f'model-{i}',
       'variant': '51 mm, AMOLED, Solar, inReach' if i%2 else '', 'calculated_status':'VERIFIED',
       'attempted_install_count':i+10,'successful_install_count':i+10-(1 if i<10 else 0),'failed_install_count':1 if i<10 else 0,
       'last_success':None if i%7==0 else '2026-09-17T10:20:00Z','last_evidence':'2026-09-17T10:30:00Z'} for i in range(120)]
    events=[{'event_id':f'fixture-{i}', 'operation_id':f'op-{i}', 'map_result_index':0,'model':rows[i%120]['model'],
        'compatibility_identity':f'model-{i%120}','canonical_device_model_id':f'model-{i%120}', 'phase_outcome':'FAILED' if i%10==0 else 'SUCCEEDED',
        'automatic_finishing_result':'VERIFIED','write_started':True,'diagnostic_status':'ACTIVE','occurred_at':'2026-09-17T10:30:00Z',
        'provider':'custom' if i%5==0 else 'freizeitkarte', 'region':'custom' if i%5==0 else 'LT'} for i in range(3000)]
    summary=_diagnostic_summary_by_identity(events)
    providers=[{'id':k,'name':n,'status':'ACTIVE','health':'HEALTHY','packageCount':180,'affectedPackageCount':0,'problematicSourceCount':0,
        'lastHealthCheck':'2026-09-17T10:30:00Z','lastCatalogSync':'2026-09-16T10:30:00Z','lastCollectionStatus':'SUCCEEDED','lastCollectionSuccess':'2099-01-01T00:00:00Z','latestRelease':'2026-09-15'} for k,n in [('freizeitkarte','Freizeitkarte'),('opentopomap','OpenTopoMap'),('long','Provider With A Very Long Real Name')]]
    stats={'rows':[{'provider_id':'freizeitkarte','map_package_id':'lt','region':'LT','region_country':'LT','region_identity':'lt','display_name':'Lithuania',
        'component_kind':'main','event_type':'INSTALL_SUCCEEDED','outcome':'SUCCEEDED','operation_count':3000,'event_count':3000,'last_occurred_at':'2026-09-17T10:30:00Z'}], 'summary':{'hasEventData':True,'completedDownloads':3000,'completedInstalls':3000,'failedInstalls':0,'downloadSuccessRate':100,'installSuccessRate':100}}
    stats['rows'] += [{'provider_id':'custom','event_type':'INSTALL_SUCCEEDED','outcome':'SUCCEEDED','operation_count':15,'event_count':15},
        {'provider_id':'freizeitkarte','region':'unknown','event_type':'INSTALL_SUCCEEDED','outcome':'SUCCEEDED','operation_count':1,'event_count':1}]
    stats["summary"] = _map_statistics_summary(stats["rows"])
    recent=[]
    for i,kind in enumerate(('DOWNLOAD_STARTED','DOWNLOAD_PROCESSING','DOWNLOAD_CANCELLED','DOWNLOAD_INTERRUPTED','DOWNLOAD_SUCCEEDED','DOWNLOAD_FAILED','INSTALL_SUCCEEDED','INSTALL_FAILED','MAP_UPDATE_SUCCEEDED','MAP_UPDATE_FAILED')):
        recent.append({'event_type':kind,'provider_id':'freizeitkarte','map_package_id':'lt','region':'Lithuania','occurred_at':'2026-09-17T10:30:00Z','component_kind':'main'})
    recent[4]['lifecycle']=[{'type':'DOWNLOAD_STARTED','at':'2026-09-17T10:20:00Z'},{'type':'DOWNLOAD_PROCESSING','at':'2026-09-17T10:25:00Z'},{'type':'DOWNLOAD_SUCCEEDED','at':'2026-09-17T10:30:00Z'}]
    recent[6]['model']='fēnix 8'
    recent[6]['variant']='51 mm, AMOLED'
    recent[6]['canonical_device_model_id']='model-0'
    recent[6]['device_link_state']='LINKED'
    overview_trend=[{'bucket':f'2026-09-{day:02d}T00:00:00Z','download_success_count':7+day%5,'download_failed_count':1 if day in {20,23} else 0,'success_count':5+day%4,'failed_count':1 if day in {19,22,24} else 0,'custom_count':0,'map_update_count':1 if day==24 else 0} for day in range(18,25)]
    app_download_trend=[{'bucket':f'2026-09-{day:02d}T00:00:00Z','observed_at':f'2026-09-{day:02d}T18:00:00Z','state':'observed_increase','dmg_count':6+day%4,'zip_count':2+day%2,'confidence':'verified','population_comparability':'verified'} for day in range(18,25)]
    overview={'period':'30d','data':{'hasData':True,'allTimeSuccessCount':56,'allTimeFailedCount':9,'allTimeInstallSuccessRate':86.2,'allTimeCompletedDownloadCount':84,'allTimeFailedDownloadCount':4,'allTimeDownloadSuccessRate':95.5,'allTimeCustomCount':15,'allTimeMapUpdateCount':0,'eventCount':3000,'completedInstallCount':2700,'failedInstallCount':300,'installSuccessRate':90,'completedDownloadCount':70,'failedDownloadCount':3,'downloadSuccessRate':95.9,'trend':overview_trend,'bucket':'day','recentActivity':recent},
        'downloads':{'hasData':True,'dmgTotal':326,'zipTotal':84,'lastObservedAt':'2026-09-24T18:00:00Z','lastSuccessfulObservedAt':'2026-09-24T18:00:00Z','bucket':'day','trend':app_download_trend},
        'providers':providers,'compatibility':{'hasData':True,'allTimeOpenErrorCount':20,'recentActivity':[dict(events[0],operation_key='fixture-0',last_occurred_at='2026-09-17T10:30:00Z')],
        'attention':[dict(events[i],operation_key=f'fixture-{i}',open_error=True,has_failed=True,error_category='TRANSFER_FAILED',last_occurred_at='2026-09-17T10:30:00Z') for i in range(40)]}}
    overview['data'].update({'completedMapUpdateCount':38,'failedMapUpdateCount':1,'mapUpdateCount':39,
        'allTimeMapUpdateSuccessCount':120,'allTimeMapUpdateFailedCount':3,
        'downloadPurposes':{'install':{'succeeded':52,'failed':2},'update':{'succeeded':12,'failed':1},'unknown':{'succeeded':6,'failed':0}}})
    for item in overview_trend:
        item.setdefault('map_update_success_count', 1 if item['bucket'].endswith('24T00:00:00Z') else 0)
        item['custom_count'] = 1 if item['bucket'].endswith(('20T00:00:00Z','23T00:00:00Z')) else 0
    # Period tiles describe the same population as the chart beside them.
    def _trend_total(*fields):
        return sum(int(item.get(field) or 0) for item in overview_trend for field in fields)
    installs, failed_installs = _trend_total('success_count', 'custom_count'), _trend_total('failed_count')
    updates, failed_updates = _trend_total('map_update_success_count'), _trend_total('map_update_failed_count')
    downloads, failed_downloads = _trend_total('download_success_count'), _trend_total('download_failed_count')
    overview['data'].update({
        'completedInstallCount': installs, 'failedInstallCount': failed_installs,
        'installSuccessRate': installs / (installs + failed_installs) * 100,
        'completedMapUpdateCount': updates, 'failedMapUpdateCount': failed_updates,
        'mapUpdateCount': updates + failed_updates,
        'completedDownloadCount': downloads, 'failedDownloadCount': failed_downloads,
        'downloadSuccessRate': downloads / (downloads + failed_downloads) * 100,
        'downloadPurposes': {'install': {'succeeded': downloads - 6 - 12, 'failed': failed_downloads - 1},
                             'update': {'succeeded': 12, 'failed': 1},
                             'unknown': {'succeeded': 6, 'failed': 0}},
    })
    overview['funnel']={'sessionCount':42,'neverConnectedSessionCount':4,'stages':[
        {'stage':'DEVICE_CONNECT','outcomes':[{'outcome':'CONNECTED','sessionCount':38},{'outcome':'TIMEOUT_NO_USB','sessionCount':5},{'outcome':'NOT_MTP_MODE','sessionCount':3},{'outcome':'BUSY','sessionCount':1},{'outcome':'DISCONNECTED','sessionCount':2}]},
        {'stage':'AUTHORIZATION','outcomes':[{'outcome':'APPROVED','sessionCount':30},{'outcome':'PENDING','sessionCount':5},{'outcome':'UNKNOWN_MODEL','sessionCount':2},{'outcome':'AMBIGUOUS','sessionCount':1}]},
        {'stage':'CATALOG','outcomes':[{'outcome':'REMOTE','sessionCount':36},{'outcome':'REMOTE_PARTIAL','sessionCount':3},{'outcome':'BUNDLED_FALLBACK','sessionCount':2},{'outcome':'UPDATE_REQUIRED','sessionCount':0}]},
        {'stage':'INSTALL_BLOCKED','outcomes':[{'outcome':'AUTHORIZATION','sessionCount':5},{'outcome':'DEVICE_STORAGE','sessionCount':2},{'outcome':'LOCAL_CAPABILITY','sessionCount':1},{'outcome':'OTHER','sessionCount':0}]}],
        'modelsNeedingReview':[{'baseModel':'fenix 8','outcome':'PENDING','sessionCount':4},{'baseModel':'Forerunner 965','outcome':'UNKNOWN_MODEL','sessionCount':1}]}
    overview['supportReports']={'openCount':3}
    overview['mapsUnknown']={'modelCount':2}
    # One failed scheduler heartbeat: Needs attention shows one System checks row.
    overview['system']={'api':'HEALTHY','database':'HEALTHY','providers':providers,'observations':[],'weekly':None,
                        'scheduler':{'status':'FAILED','error_summary':'Catalog collector exited with an error.','updated_at':'2026-09-17T10:30:00Z'}}
    device=_admin_device_payload([{'device_id':'model-0','model':'fēnix 8','variant':'51 mm, AMOLED','family_name':'fēnix','map_capable':True,'active':True,'support_status':'SUPPORTED','usb_identities':[]}],None)['devices'][0]
    detail,provider_runs,provider_audits=_provider_detail_fixture(providers[0])
    # The list exercises a positive Issues cell next to measured zeros.
    provider_list=[*providers[:2],dict(providers[2],health='DEGRADED',affectedPackageCount=2,problematicSourceCount=2)]
    pages={'overview':overview_page(overview,user,'fixture'),'installations':dashboard_page(rows,user,'fixture',diagnostic_summary=summary),
       'providers':providers_page(provider_list,user,'fixture'),'provider':provider_detail_page({'provider':detail},provider_runs,provider_audits,user,'fixture'),
       'statistics':map_statistics_page(stats,providers,user,'fixture'),'device':device_detail_page(device,user,'fixture'),'devices':devices_page([],None,user,'fixture')}
    # 50 checks spread over the four Health groups (Technical details tabs).
    cards=[_system_health_card(f'Check {i+1}', 'FAILED' if i<5 else 'WARNING' if i<10 else 'HEALTHY', '<p>Packages: 180</p>', {'observed_at':'2026-09-17T10:30:00Z'},reason='Catalog request timed out' if i<10 else '',action='Inspect collection history',group=('service','releases','catalogs','search')[i%4]) for i in range(50)]
    cards.append(_indexnow_card({
        'status':'WARNING', 'observed_at':'2026-09-17T10:30:00Z',
        'source_run_url':'https://github.com/VooZ2/terento/actions/runs/321',
        'details': {
            'result':'validation_pending', 'publication_id':'deployment-site-321-1',
            'last_submission_at':'2026-09-17T10:25:00Z',
            'last_successful_submission_at':None, 'attempted_url_count':1,
            'http_200_count':0, 'http_202_count':1, 'http_status':202,
            'pending_url_count':1, 'oldest_pending_at':'2026-09-17T10:25:00Z',
            'error_summary':'A deliberately long validation message remains readable while the expanded card wraps safely across narrow layouts.',
            'url_preview':'https://terento.app/\nhttps://terento.app/guides/install-garmin-maps-mac/',
            'url_preview_total':2,
        },
    }, None, now=datetime(2026, 9, 17, 10, 31, tzinfo=timezone.utc)))
    with patch('terento_catalog.admin._system_health_cards',return_value=(cards,None,{})):
        pages['health']=system_health_page({},user,'fixture')
    for name,body in pages.items():
        (root/(name+'.html')).write_bytes(body.replace(
            b'https://terento.app/assets/fonts/', b'/admin/fonts/',
        ))
    # Signed-in pages link the content-versioned Admin stylesheet and world map.
    (root / ADMIN_STYLESHEET_PATH.lstrip('/')).parent.mkdir(parents=True, exist_ok=True)
    (root / ADMIN_STYLESHEET_PATH.lstrip('/')).write_text(
        ADMIN_STYLES.replace('https://terento.app/assets/fonts/', '/admin/fonts/'), encoding='utf-8')
    (root / WORLD_MAP_SCRIPT_PATH.lstrip('/')).write_text(WORLD_MAP_SCRIPT, encoding='utf-8')
    return pages

if __name__=='__main__':
    import sys
    build(sys.argv[1])
