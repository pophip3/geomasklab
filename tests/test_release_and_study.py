"""Reject unconfirmed attribution and empty or duplicated study observations.

All response rows here are fictional unit-test fixtures, never study observations.
"""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from evaluation.analyze_handoff_study import analyze
from release.prepare_metadata import metadata


class ReleaseAndStudy(unittest.TestCase):
    def test_release_metadata_requires_confirmed_creators_and_valid_orcid(self):
        with self.assertRaises(ValueError):metadata({'confirmed':False,'creators':[]},'1.0.0')
        fixture={'confirmed':True,'release_date':'2026-10-05','creators':[{'given_names':'Fictional','family_names':'Unit Test'}]}
        citation,archive=metadata(fixture,'1.0.0rc1')
        self.assertNotIn('doi',citation);self.assertEqual(archive['creators'][0]['name'],'Unit Test, Fictional')
        fixture['creators'][0]['orcid']='0000-0000-0000-0000'
        with self.assertRaisesRegex(ValueError,'checksum'):metadata(fixture,'1.0.0')
        fixture['creators'][0]['orcid']='0000-0002-1825-0097'
        self.assertEqual(metadata(fixture,'1.0.0')[0]['authors'][0]['orcid'],'https://orcid.org/0000-0002-1825-0097')

    def test_empty_study_is_not_reported_as_success_and_duplicates_fail(self):
        fields=['participant_id','case_id','condition','elapsed_seconds','foreground_pixels',
                'selected_region_pixels','whole_image_pixels','whole_image_coverage','within_region_coverage','inference_performed']
        answer={'case_id':'A','foreground_pixels':2,'selected_region_pixels':4,'whole_image_pixels':8,
                'whole_image_coverage':.25,'within_region_coverage':.5}
        fictional={'participant_id':'unit-fixture','case_id':'A','condition':'evidence','elapsed_seconds':10,
                   **{k:v for k,v in answer.items() if k!='case_id'},'inference_performed':'false'}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);key=root/'key.json';observations=root/'observations.csv'
            key.write_text(json.dumps([answer]),encoding='utf-8')
            def write(rows):
                with observations.open('w',newline='',encoding='utf-8') as handle:
                    writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(rows)
            write([])
            with self.assertRaisesRegex(ValueError,'No participant'):analyze(observations,key)
            write([fictional,fictional])
            with self.assertRaisesRegex(ValueError,'Duplicate'):analyze(observations,key)
            write([fictional]);result=analyze(observations,key)
            self.assertEqual(result['conditions']['evidence']['fully_correct'],1)
            self.assertIsNone(result['conditions']['loose-files']['error_rate'])
            fictional['whole_image_pixels']=4;write([fictional])
            self.assertEqual(analyze(observations,key)['conditions']['evidence']['error_rate'],1)


if __name__=='__main__':unittest.main()
