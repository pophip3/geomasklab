"""Mandatory replay must distinguish pixel counts from JSON Boolean values."""
from copy import deepcopy
import io
import json
import unittest

import _source_package
_source_package.use_local_core()
from PIL import Image
from geomasklab.api import create_evidence
from geomasklab.domain import png
from geomasklab.evidence import bundle_contents, load_verified_bundle


class EvidenceNumericTypes(unittest.TestCase):
    def bundle(self, *, validity=False, empty=False, size=(1, 2), roi=True):
        image = png(Image.new('RGB', size, (17, 31, 47)))
        mask = Image.new('L', size)
        if not empty:
            mask.putpixel((0, 0), 255)
        options = {}
        if roi:
            options['roi'] = {'xyxy': [0, 0, 1, 1], 'source': 'imported', 'image_size': list(size)}
        if validity:
            options.update(valid_mask=png(Image.new('L', size, 255)), valid_source='Explicit all-valid numeric type fixture.')
        return create_evidence(image, png(mask), target='tree', source='Hand-defined pixel-count fixture.', aligned=True, **options)

    def changed(self, payload, path, value, *, sync_result=True):
        """Change a declared field and update every hash without altering pixels."""
        _, files = load_verified_bundle(payload)
        stats = json.loads(files['statistics.json'])
        result = json.loads(files['result.json'])
        target = stats
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        files['statistics.json'] = json.dumps(stats, allow_nan=True).encode()
        if sync_result:
            result['metrics'] = deepcopy(stats)
            files['result.json'] = json.dumps(result, allow_nan=True).encode()
        return bundle_contents(files)

    def assert_rejected(self, payload, path, value, *, sync_result=True):
        raw = self.changed(payload, path, value, sync_result=sync_result)
        # No jsonschema import, optional extra, or CLI --schema flag is involved.
        with self.assertRaises(ValueError):
            load_verified_bundle(raw)

    def test_rehashed_boolean_counts_dimensions_and_bbox_are_rejected_in_both_schemas(self):
        mutations = [('pixel_area', True), ('width', True), ('scope_area_pixels', True),
                     ('bbox_xyxy', [False, 0, 1, 1]), ('bbox_xyxy', [0, 0, True, 1])]
        for validity in (False, True):
            payload = self.bundle(validity=validity)
            for field, value in mutations:
                with self.subTest(validity=validity, field=field, value=value):
                    self.assert_rejected(payload, [field], value)
            empty = self.bundle(validity=validity, empty=True)
            with self.subTest(validity=validity, field='zero_pixel_area'):
                self.assert_rejected(empty, ['pixel_area'], False)
            single = self.bundle(validity=validity, size=(1, 1), roi=False)
            for field in ('total_pixels', 'width', 'height'):
                with self.subTest(validity=validity, field=field):
                    self.assert_rejected(single, [field], True)

    def test_integer_count_fields_reject_integral_floats(self):
        for validity in (False, True):
            payload = self.bundle(validity=validity)
            for path in (['pixel_area'], ['width'], ['scope_area_pixels'],
                         ['distribution', 'right_pixels'], ['candidate_stats', 'candidate_count'],
                         ['candidate_stats', 'candidates', 0, 'area_pixels'],
                         ['candidate_stats', 'candidates', 0, 'bbox', 'width']):
                with self.subTest(validity=validity, path=path):
                    self.assert_rejected(payload, path, 1.0)

    def test_distribution_counts_reject_boolean_zero_and_one(self):
        for validity in (False, True):
            payload = self.bundle(validity=validity)
            for field, value in [('left_pixels', False), ('right_pixels', True),
                                 ('roi_inside_pixels', True), ('roi_outside_pixels', False)]:
                with self.subTest(validity=validity, field=field):
                    self.assert_rejected(payload, ['distribution', field], value)

    def test_every_candidate_numeric_structure_rejects_booleans(self):
        mutations = [(['candidate_count'], True), (['raw_candidate_count'], True),
            (['filtered_out_count'], False), (['total_area_pixels'], True),
            (['min_area'], True), (['max_area'], True), (['mean_area'], True),
            (['min_area_pixels'], True), (['connectivity'], True),
            (['candidates', 0, 'candidate_id'], True), (['candidates', 0, 'area_pixels'], True),
            (['candidates', 0, 'bbox', 'x'], False), (['candidates', 0, 'bbox', 'y'], False),
            (['candidates', 0, 'bbox', 'width'], True), (['candidates', 0, 'bbox', 'height'], True),
            (['candidates', 0, 'center', 'x'], False), (['candidates', 0, 'center', 'y'], False)]
        for validity in (False, True):
            payload = self.bundle(validity=validity)
            for path, value in mutations:
                with self.subTest(validity=validity, path=path):
                    self.assert_rejected(payload, ['candidate_stats', *path], value)

    def test_metric_document_equality_is_type_aware(self):
        for validity in (False, True):
            payload = self.bundle(validity=validity, empty=True)
            with self.subTest(validity=validity):
                # result.json still contains integer 0; only statistics.json is
                # changed to false. Ordinary Python dictionary equality equates them.
                self.assert_rejected(payload, ['pixel_area'], False, sync_result=False)

    def test_geometric_ratios_reject_boolean_and_nonfinite_values(self):
        for validity in (False, True):
            single = self.bundle(validity=validity, size=(1, 1), roi=False)
            empty = self.bundle(validity=validity, empty=True)
            for field in ('area_ratio', 'scope_area_ratio'):
                with self.subTest(validity=validity, field=field, value=True):
                    self.assert_rejected(single, [field], True)
                with self.subTest(validity=validity, field=field, value=False):
                    self.assert_rejected(empty, [field], False)
                for value in (float('nan'), float('inf'), float('-inf')):
                    with self.subTest(validity=validity, field=field, value=value):
                        self.assert_rejected(single, [field], value)

    def test_roi_endpoints_and_declared_image_dimensions_reject_boolean_values(self):
        for validity in (False, True):
            for field, value in [('xyxy', [False, 0, 1, 1]), ('xyxy', [0, 0, True, 1]),
                                 ('image_size', [True, 2])]:
                payload = self.bundle(validity=validity)
                _, files = load_verified_bundle(payload)
                result = json.loads(files['result.json'])
                stats = json.loads(files['statistics.json'])
                for roi in (result['task']['roi'], result['task_options']['roi'], stats['roi']):
                    roi[field] = value
                result['metrics'] = stats
                if validity:
                    config = json.loads(files['analysis.json'])
                    config['roi'][field] = value
                    result['analysis_config'] = config
                    files['analysis.json'] = json.dumps(config).encode()
                files['result.json'] = json.dumps(result).encode()
                files['statistics.json'] = json.dumps(stats).encode()
                with self.subTest(validity=validity, field=field), self.assertRaises(ValueError):
                    load_verified_bundle(bundle_contents(files))

    def test_declared_validity_counts_reject_boolean_values(self):
        payload = self.bundle(validity=True)
        for field in ('foreground_pixels', 'geometric_region_pixels', 'valid_region_pixels', 'excluded_region_pixels'):
            _, files = load_verified_bundle(payload)
            stats = json.loads(files['statistics.json'])
            original = stats['validity_measurements'][field]
            if original not in (0, 1):
                continue
            with self.subTest(field=field):
                self.assert_rejected(payload, ['validity_measurements', field], bool(original))

    def test_legitimate_integer_and_float_ratio_encodings_remain_compatible(self):
        for validity in (False, True):
            payload = self.bundle(validity=validity, size=(1, 1), roi=False)
            for field in ('area_ratio', 'scope_area_ratio'):
                with self.subTest(validity=validity, field=field):
                    facts, _ = load_verified_bundle(self.changed(payload, [field], 1))
                    self.assertEqual(facts['pixel_area'], 1)
            for path, value in [(['candidate_stats', 'mean_area'], 1),
                                (['candidate_stats', 'candidates', 0, 'center', 'x'], 0),
                                (['candidate_stats', 'candidates', 0, 'center', 'y'], 0)]:
                with self.subTest(validity=validity, path=path):
                    facts, _ = load_verified_bundle(self.changed(payload, path, value))
                    self.assertEqual(facts['pixel_area'], 1)
            empty = self.bundle(validity=validity, empty=True)
            facts, _ = load_verified_bundle(self.changed(empty, ['area_ratio'], 0.0))
            self.assertEqual(facts['pixel_area'], 0)


if __name__ == '__main__':
    unittest.main()
