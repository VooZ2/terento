"""Build isolated Admin scale fixtures; never submits telemetry or admin actions."""
from pathlib import Path
from unittest.mock import patch
from terento_catalog.admin import *
from terento_catalog.admin import _admin_device_payload, _system_health_card, _diagnostic_summary_by_identity, _map_statistics_summary


def build(root):
    root=Path(root); user={'username':'Preview', 'admin_review_summary':{'available':True,'installationIssues':20,'githubIssuesInProgress':5,'identityPending':12,'readyToPublish':3,'total':40}}
    rows=[{'model':f'fēnix {i+1} Very Long Authentic Model Name', 'compatibility_identity':f'model-{i}', 'canonical_device_model_id':f'model-{i}',
       'variant': '51 mm, AMOLED, Solar, inReach' if i%2 else '', 'calculated_status':'VERIFIED',
       'attempted_install_count':i+10,'successful_install_count':i+9,'failed_install_count':1,
       'last_success':None if i%7==0 else '2026-09-17T10:20:00Z','last_evidence':'2026-09-17T10:30:00Z'} for i in range(120)]
    events=[{'event_id':f'fixture-{i}', 'operation_id':f'op-{i}', 'map_result_index':0,'model':rows[i%120]['model'],
        'compatibility_identity':f'model-{i%120}','canonical_device_model_id':f'model-{i%120}', 'phase_outcome':'FAILED' if i%10==0 else 'SUCCEEDED',
        'automatic_finishing_result':'VERIFIED','write_started':True,'diagnostic_status':'ACTIVE','occurred_at':'2026-09-17T10:30:00Z',
        'provider':'custom' if i%5==0 else 'freizeitkarte', 'region':'custom' if i%5==0 else 'LT'} for i in range(3000)]
    summary=_diagnostic_summary_by_identity(events)
    metric={'averageSeconds':277.4,'sampleCount':2800,'populationCount':3000}
    providers=[{'id':k,'name':n,'status':'ACTIVE','health':'HEALTHY','packageCount':180,'affectedPackageCount':0,'problematicSourceCount':0,
        'downloadTime':metric,'lastHealthCheck':'2026-09-17T10:30:00Z','lastCatalogSync':'2026-09-16T10:30:00Z'} for k,n in [('freizeitkarte','Freizeitkarte'),('opentopomap','OpenTopoMap'),('long','Provider With A Very Long Real Name')]]
    stats={'rows':[{'provider_id':'freizeitkarte','map_package_id':'lt','region':'LT','region_country':'LT','region_identity':'lt','display_name':'Lithuania',
        'component_kind':'main','event_type':'INSTALL_SUCCEEDED','outcome':'SUCCEEDED','operation_count':3000,'event_count':3000,'last_occurred_at':'2026-09-17T10:30:00Z'}], 'downloadTimes':{'freizeitkarte':metric},'summary':{'hasEventData':True,'completedDownloads':3000,'completedInstalls':3000,'failedInstalls':0,'downloadSuccessRate':100,'installSuccessRate':100}}
    stats["summary"] = _map_statistics_summary(stats["rows"])
    recent=[]
    for i,kind in enumerate(('DOWNLOAD_STARTED','DOWNLOAD_PROCESSING','DOWNLOAD_CANCELLED','DOWNLOAD_INTERRUPTED','DOWNLOAD_SUCCEEDED','DOWNLOAD_FAILED','INSTALL_SUCCEEDED','INSTALL_FAILED','MAP_UPDATE_SUCCEEDED','MAP_UPDATE_FAILED')):
        recent.append({'event_type':kind,'provider_id':'freizeitkarte','map_package_id':'lt','region':'Lithuania','occurred_at':'2026-09-17T10:30:00Z','component_kind':'main'})
    recent[4]['lifecycle']=[{'type':'DOWNLOAD_STARTED','at':'2026-09-17T10:20:00Z'},{'type':'DOWNLOAD_PROCESSING','at':'2026-09-17T10:25:00Z'},{'type':'DOWNLOAD_SUCCEEDED','at':'2026-09-17T10:30:00Z'}]
    overview={'period':'30d','data':{'hasData':True,'eventCount':3000,'completedInstallCount':2700,'failedInstallCount':300,'installSuccessRate':90,'recentActivity':recent},
        'providers':providers,'compatibility':{'hasData':True,'allTimeOpenErrorCount':20,'recentActivity':[dict(events[0],operation_key='fixture-0',last_occurred_at='2026-09-17T10:30:00Z')],
        'attention':[dict(events[i],operation_key=f'fixture-{i}',open_error=True,has_failed=True,error_category='TRANSFER_FAILED',last_occurred_at='2026-09-17T10:30:00Z') for i in range(40)]}}
    device=_admin_device_payload([{'device_id':'model-0','model':'fēnix 8','variant':'51 mm, AMOLED','family_name':'fēnix','map_capable':True,'active':True,'support_status':'SUPPORTED','usb_identities':[]}],None)['devices'][0]
    detail=dict(providers[0],maps=[],sources=[],healthStatus='HEALTHY',healthHistory=[{'status':'HEALTHY','checked_at':'2026-09-17T10:30:00Z','http_status':200,'duration_ms':125,'artifact_count':180}],activationGate={'canActivate':True})
    pages={'overview':overview_page(overview,user,'fixture'),'installations':dashboard_page(rows,user,'fixture',diagnostic_summary=summary),
       'providers':providers_page(providers,user,'fixture'),'provider':provider_detail_page({'provider':detail},[{'id':1,'status':'SUCCEEDED','package_count':180,'artifact_count':180,'finished_at':'2026-09-17T10:20:00Z'}],[],user,'fixture'),
       'statistics':map_statistics_page(stats,providers,user,'fixture'),'device':device_detail_page(device,user,'fixture'),'devices':devices_page([],None,user,'fixture')}
    cards=[_system_health_card(f'Check {i+1}', 'FAILED' if i<5 else 'WARNING' if i<10 else 'HEALTHY', '<p>Packages: 180</p>', {'observed_at':'2026-09-17T10:30:00Z'},reason='Catalog request timed out' if i<10 else '',action='Inspect collection history') for i in range(50)]
    with patch('terento_catalog.admin._system_health_cards',return_value=(cards,None,{})):
        pages['health']=system_health_page({},user,'fixture')
    for name,body in pages.items():
        (root/(name+'.html')).write_bytes(body)
    return pages

if __name__=='__main__':
    import sys
    build(sys.argv[1])
