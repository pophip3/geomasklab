"""A deterministic PROV-JSON mapping of already verified measurement evidence.

PROV-JSON is the W3C Member Submission serialization of the PROV data model.
The mapping does not authenticate caller assertions or reconstruct missing history.
"""
import hashlib
import json
from ._version import VERSION
from .evidence import load_verified_bundle


def provenance_document(payload,*,exporter_version=VERSION):
    """Map files, pixel domain, recorded measurement and immediate derivation."""
    facts,files=load_verified_bundle(payload)
    result=json.loads(files['result.json'])
    metrics=json.loads(files['statistics.json'])
    entities={}
    names={}
    for name,raw in sorted(files.items()):
        identifier='gml:'+name.replace('.','_')
        names[name]=identifier
        entities[identifier]={'prov:label':name,'gml:sha256':hashlib.sha256(raw).hexdigest(),'gml:bytes':len(raw)}
    entities['gml:evidence']={'prov:label':'Verified source evidence ZIP',
        'gml:sha256':hashlib.sha256(payload).hexdigest(),'gml:format':facts['schema'],
        'gml:verificationScope':'Internal consistency; no semantic accuracy or authenticated source claim'}
    entities['gml:domain']={'prov:label':'Explicit measurement domain',
        'gml:definition':json.dumps(result['task'],sort_keys=True,separators=(',',':')),
        'gml:wholeImagePixels':metrics['total_pixels']}
    if 'scope_area_pixels' in metrics:entities['gml:domain']['gml:selectedRegionPixels']=metrics['scope_area_pixels']
    entities['gml:asserted_source']={'prov:label':'Caller-supplied source assertions',
        'gml:record':json.dumps({'image':result['provenance'],'external_mask':result.get('external_mask'),
            'source_prediction':result.get('source_prediction')},sort_keys=True,separators=(',',':')),
        'gml:authenticated':False}
    activities={'gml:measurement':{'prov:label':'Recorded scoped pixel measurement',
        'gml:softwareVersion':result.get('software_version','unrecorded'),
        'gml:executionKind':result.get('execution_kind',result['mode'])},
        'gml:mapping':{'prov:label':'Verified evidence to PROV-JSON mapping','gml:softwareVersion':exporter_version}}
    # Preserve the source timestamp without promoting it to an authenticated event time.
    if result.get('created_at'):activities['gml:measurement']['gml:recordedAt']=result['created_at']
    doc={'prefix':{'gml':'urn:geomasklab:provenance:','prov':'http://www.w3.org/ns/prov#'},
        'entity':entities,'activity':activities,
        'agent':{'gml:software':{'prov:type':{'$':'prov:SoftwareAgent','type':'prov:QUALIFIED_NAME'},
            'prov:label':'GeoMaskLab'}},
        'used':{'_:mask':{'prov:activity':'gml:measurement','prov:entity':names['full_mask.png']},
                '_:image':{'prov:activity':'gml:measurement','prov:entity':names['original.png']},
                '_:domain':{'prov:activity':'gml:measurement','prov:entity':'gml:domain'},
                '_:bundle':{'prov:activity':'gml:mapping','prov:entity':'gml:evidence'}},
        'wasGeneratedBy':{'_:statistics':{'prov:entity':names['statistics.json'],'prov:activity':'gml:measurement'},
                          '_:mask':{'prov:entity':names['mask.png'],'prov:activity':'gml:measurement'}},
        'wasDerivedFrom':{'_:scoped':{'prov:generatedEntity':names['mask.png'],'prov:usedEntity':names['full_mask.png']}},
        'wasAssociatedWith':{'_:software':{'prov:activity':'gml:mapping','prov:agent':'gml:software'}}}
    if 'source_mask.png' in names:
        doc['wasDerivedFrom']['_:normalized']={'prov:generatedEntity':names['full_mask.png'],'prov:usedEntity':names['source_mask.png']}
    if 'analysis.json' in names:
        doc['used']['_:validity']={'prov:activity':'gml:measurement','prov:entity':names['valid_mask.png']}
        doc['used']['_:configuration']={'prov:activity':'gml:measurement','prov:entity':names['analysis.json']}
    parent=result.get('derived_from')
    if parent:
        entities['gml:parent_evidence']={'prov:label':'Immediate parent evidence (identity only)',
            'gml:sha256':parent['bundle_sha256'],'gml:embedded':False}
        doc['wasDerivedFrom']['_:parent']={'prov:generatedEntity':'gml:evidence','prov:usedEntity':'gml:parent_evidence'}
    return doc


def verify_provenance(payload,document):
    """Replay the source bundle and compare the entire exported mapping."""
    try:version=document['activity']['gml:mapping']['gml:softwareVersion']
    except (KeyError,TypeError) as error:raise ValueError('PROV-JSON exporter version is missing.') from error
    if not isinstance(version,str) or not version or len(version)>64:raise ValueError('Invalid recorded PROV-JSON exporter version.')
    if document!=provenance_document(payload,exporter_version=version):raise ValueError('PROV-JSON mapping does not match the verified source evidence.')
    return {'verified':True,'evidence_sha256':hashlib.sha256(payload).hexdigest(),
            'scope':'Deterministic mapping and source consistency; no authenticity claim'}
