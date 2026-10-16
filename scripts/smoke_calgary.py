"""Hosted v3 equipment acceptance with synthetic records; no forced AI call."""
import sys,json,uuid,time
from pathlib import Path
from datetime import date
import httpx
checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name);print('PASS',name,flush=True)
with httpx.Client(base_url=sys.argv[1],timeout=160) as c:
    check('PostgreSQL v3 health',c.get('/api/health').json().get('version')=='3.0')
    c.post('/api/demo/start').raise_for_status();session=c.get('/api/session').json()
    def switch(name):c.post('/api/accounts/switch',json={'name':name}).raise_for_status()
    assets=c.get('/api/assets').json();a=next(a for a in assets if a['code']=='LM-1042')
    check('Model distinct from product number',a['model']=='RP-460HD' and a['product_number']=='L015-201')
    check('Technician cannot administer',c.get('/api/operations').status_code==403)
    switch('Demo super-user');check('Calgary-only administration',c.get('/api/operations').json()['location']=='Calgary')
    p=c.post('/api/procedures',json={'title':'Hosted synthetic observation checklist','manufacturer':'Lemmer','model':a['model'],'product_number':a['product_number'],'symptoms':['Fluid seeps around the needle packing after use.'],'steps':[{'question':'Has the visible symptom been recorded without operating the equipment?','yes':-1,'no':-1,'unknown':-1}],'references':[{'title':'Synthetic workflow fixture','passage':'This test confirms observation persistence only, not a repair instruction.','page':'Unknown','revision':'Smoke 1'}],'solution':'Record actual technician findings and verification separately.','synthetic':True});p.raise_for_status();p=p.json()
    check('Procedure initially pending',p['status']=='Pending review')
    c.post('/api/procedures/'+p['id']+'/review',json={'status':'Approved','reason':'Synthetic checklist and privacy confirmed for smoke test.','technical_checked':True,'privacy_checked':True}).raise_for_status()
    switch('Taylor Brooks')
    customer=c.post('/api/customers',json={'name':'Synthetic Calgary acceptance owner','sap_customer_code':'SMOKE-'+uuid.uuid4().hex[:8]}).json()
    registered=[]
    for i in range(2):
        x=c.post('/api/registry',json={'customer_id':customer['id'],'customer_confirmed':True,'name':'Synthetic equipment '+str(i),'model':'RP-460HD','product_sku':'L015-201','serial':'SMOKE-'+str(i),'sap_document_type':'Invoice','sap_document_number':'DEMO-INV','sap_line_number':str(i+1)})
        x.raise_for_status();registered.append(x.json())
    check('Second asset gets unique identity',registered[0]['id']!=registered[1]['id'] and registered[0]['code']!=registered[1]['code'])
    found=next(x for x in c.get('/api/customers').json() if x['id']==customer['id'])
    check('SAP / previous asset owner lookup available',found['sap_customer_code'] and registered[0]['code'] in found['asset_codes'] and found['asset_count']==2)
    intake={'asset_id':a['id'],'title':'Synthetic visible seepage','description':'Fluid seeps around the needle packing after use.','category':'Inspection','name':'Synthetic dropoff employee','email':'','technician':'Alex Morgan','reviewed':False,'submission_id':str(uuid.uuid4()),'accessories':'Gun and cup','visible_damage':'Not assessed','customer_instructions':'Record observations only.','dropoff_role':'Employee'}
    check('Review checkbox enforced',c.post('/api/intake/handoff',json=intake).status_code==422)
    intake['reviewed']=True
    check('Existing open visit warning enforced',c.post('/api/intake/handoff',json=intake).status_code==409)
    intake['acknowledge_open']=True;r=c.post('/api/intake/handoff',json=intake);r.raise_for_status();r=r.json();path='/api/requests/'+r['id']
    check('Unassessed operating default retained',r['operating']=='Unknown / Not assessed')
    check('Idempotent handoff',c.post('/api/intake/handoff',json=intake).json()['id']==r['id'])
    check('Receipt uses saved visit and permanent asset',c.get(path+'/receipt').json()['code']==r['code'])
    check('Reception cannot see internal AI review',c.get(path+'/guidance').status_code==403)
    switch('Alex Morgan')
    check('Approved procedure automatically offered',c.get(path+'/procedures').json()['procedures'][0]['id']==p['id'])
    run=c.post(path+'/procedures/'+p['id']+'/start');run.raise_for_status();run=run.json()
    answer=c.post('/api/procedure-runs/'+run['id']+'/answer',json={'version':1,'answer':'unknown','observation':'Technician needs further evidence; no replacement decision made.'})
    check('Checklist records uncertainty without AI',answer.status_code==200 and answer.json()['status']=='Completed')
    check('Checklist cannot be answered twice',c.post('/api/procedure-runs/'+run['id']+'/answer',json={'version':1,'answer':'yes','observation':'duplicate'}).status_code==409)
    report={'diagnosis':'Synthetic inspection, fault not confirmed','work':'Recorded observed symptoms for further assessment','part_lines':[],'test':'Inspection incomplete; no repair outcome claimed','outcome':'Not repaired','notes':'Awaiting technician measurements and approval.','inspection_date':date.today().isoformat(),'version':r['version'],'submission_id':str(uuid.uuid4()),'close_request':False}
    result=c.post(path+'/reports',json=report);result.raise_for_status();result=result.json()
    check('Report remains open unless deliberately closed',result['request']['status']=='In progress')
    eid=result['event']['id']
    switch('Demo super-user')
    c.post('/api/operations/corrections/'+eid,json={'kind':'report','changes':{'diagnosis':'Synthetic correction: inspection remains inconclusive'},'expected':{'diagnosis':report['diagnosis']},'reason':'Correct wording while retaining the original service report.'}).raise_for_status()
    check('Correction recorded in audit',any(x['action']=='Correct report' and x['object_id']==eid for x in c.get('/api/operations').json()['audit']))
    check('Usage ledger available',isinstance(c.get('/api/operations/usage').json()['records'],list))
    # Existing customer ownership remains private even with a known Asset ID.
    owner=next(x['name'] for x in session['accounts'] if x['role']=='customer');switch(owner)
    check('Customer cannot administer',c.get('/api/operations').status_code==403)
    check('Known other-owner asset stays private',c.get('/api/portal/assets/'+registered[0]['id']).status_code==404)
    check('Owner QR still resolves own passport',c.get('/api/qr/'+session['share']+'/'+a['code']).json()['id']==a['id'])
    Path('.local/reports/calgary-hosted-checks.json').write_text(json.dumps({'url':sys.argv[1],'checks':checks,'workspace_demo_share':session['share'],'request_id':r['id']},indent=2))
print(len(checks),'hosted checks passed')
