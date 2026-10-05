"""Generate citation and archive metadata only from explicitly confirmed creators."""
import argparse
import datetime
import json
from pathlib import Path
import re


def metadata(document,version):
    if document.get('confirmed') is not True or not document.get('creators'):
        raise ValueError('Confirmed creator names/order are required; placeholders cannot become release metadata.')
    date=document.get('release_date')
    try:datetime.date.fromisoformat(date)
    except (TypeError,ValueError) as error:raise ValueError('Supply the actual ISO release date.') from error
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:rc\d+)?',version):raise ValueError('Supply a stable or release-candidate semantic version.')
    authors=[];creators=[]
    for item in document['creators']:
        given=item.get('given_names');family=item.get('family_names')
        if any(not isinstance(v,str) or not v.strip() or re.search(r'TODO|TO BE|PLACEHOLDER|CONFIRM',v,re.I) for v in (given,family)):
            raise ValueError('Creator names must be confirmed non-placeholder strings.')
        author={'given-names':given,'family-names':family};creator={'name':family+', '+given}
        if item.get('affiliation'):author['affiliation']=item['affiliation'];creator['affiliation']=item['affiliation']
        if item.get('orcid'):
            value=item['orcid'].removeprefix('https://orcid.org/')
            if not re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]',value):raise ValueError('Invalid ORCID format.')
            digits=value.replace('-','');total=0
            for digit in digits[:15]:total=(total+int(digit))*2
            check=(12-total%11)%11
            if digits[-1]!=('X' if check==10 else str(check)):raise ValueError('Invalid ORCID checksum.')
            author['orcid']='https://orcid.org/'+value;creator['orcid']=value
        authors.append(author);creators.append(creator)
    cff={'cff-version':'1.2.0','message':'Please cite this version of GeoMaskLab and its archival DOI when available.',
         'type':'software','title':'GeoMaskLab','authors':authors,'version':version,'date-released':date,
         'license':'MIT','repository-code':'https://github.com/pophip3/geomasklab','url':'https://pophip3.github.io/geomasklab/'}
    zenodo={'title':'GeoMaskLab '+version,'upload_type':'software','description':'Model-independent scoped mask measurements, polygon domains and independently replayable evidence.',
        'creators':creators,'version':version,'publication_date':date,'license':'MIT','access_right':'open',
        'keywords':['remote sensing','segmentation masks','zonal statistics','reproducibility','provenance']}
    return cff,zenodo


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('creators',type=Path);parser.add_argument('--version',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();cff,zenodo=metadata(json.loads(args.creators.read_text(encoding='utf-8')),args.version)
    args.output.mkdir(parents=True,exist_ok=True)
    # JSON is a YAML subset, making CITATION.cff deterministic without a YAML dependency.
    (args.output/'CITATION.cff').write_text(json.dumps(cff,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (args.output/'.zenodo.json').write_text(json.dumps(zenodo,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.output),'creators':len(cff['authors']),'doi_assigned':False},indent=2))


if __name__=='__main__':main()
