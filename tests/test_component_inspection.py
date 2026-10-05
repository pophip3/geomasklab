"""Hand-counted topology and hostile-record replay for candidate inspection."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
from unittest.mock import patch
import unittest
import warnings
import zipfile

import _source_package
_source_package.use_local_core()
from PIL import Image
from geomasklab.api import create_evidence
from geomasklab.components import component_packet, inspect_components, verify_component_packet
from geomasklab.domain import png
from geomasklab.evidence import load_verified_bundle


class ComponentInspection(unittest.TestCase):
    def bundle(self, points, *, size=(8, 8), invalid=(), roi=None, scope='all', invert=False):
        image = png(Image.new('RGB', size, '#346157'))
        mask = Image.new('L', size)
        for point in points:
            mask.putpixel(point, 255)
        kwargs = {}
        if invalid:
            valid = Image.new('L', size, 255)
            for point in invalid:
                valid.putpixel(point, 0)
            kwargs.update(valid_mask=png(valid), valid_source='Hand-counted exclusion fixture')
        return create_evidence(image, png(mask), target='building', source='Hand-counted candidate fixture',
                               aligned=True, roi=roi, scope=scope, invert=invert, **kwargs)

    @staticmethod
    def files(payload):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return {name: archive.read(name) for name in archive.namelist() if name != 'manifest.json'}

    @staticmethod
    def rehash(files):
        output = io.BytesIO()
        manifest = {'schema': 'geomasklab-component-packet/1.0', 'checksums': {
            name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in files.items()}}
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
            archive.writestr('manifest.json', json.dumps(manifest))
        return output.getvalue()

    def test_diagonal_connectivity_row_major_ids_and_pixel_center_centroids(self):
        bundle = self.bundle([(6, 1), (7, 1), (2, 2), (3, 3), (1, 6)])
        record = inspect_components(bundle)
        a, b, c = record['components']
        self.assertEqual(record['foreground_pixels'], 5)
        self.assertEqual(record['component_count'], 3)
        self.assertEqual([item['component_id'] for item in (a, b, c)], [1, 2, 3])
        self.assertEqual([item['area_pixels'] for item in (a, b, c)], [2, 2, 1])
        self.assertEqual(b['bbox'], [2, 2, 4, 4])
        self.assertEqual(b['centroid'], {'x': 3.0, 'y': 3.0})
        self.assertEqual(a['centroid'], {'x': 7.0, 'y': 1.5})
        self.assertTrue(a['touches_image_boundary'])
        for item in (b, c):
            self.assertFalse(item['touches_image_boundary'])
        self.assertTrue(all(not item['touches_roi_boundary'] for item in (a, b, c)))
        self.assertTrue(all(not item['touches_invalid_boundary'] for item in (a, b, c)))
        self.assertEqual(sum(item['area_pixels'] for item in record['components']), record['foreground_pixels'])

    def test_filters_preserve_every_component_and_do_not_renumber_or_mutate(self):
        bundle = self.bundle([(6, 1), (7, 1), (2, 2), (3, 3), (1, 6)])
        original_sha = hashlib.sha256(bundle).hexdigest()
        record = inspect_components(bundle, min_area_pixels=2, boundary_filter='interior')
        self.assertEqual(record['component_count'], 3)
        self.assertEqual(record['foreground_pixels'], 5)
        self.assertEqual(record['selected_component_count'], 1)
        self.assertEqual(record['selected_foreground_pixels'], 2)
        self.assertEqual([item['component_id'] for item in record['components'] if item['selected']], [2])
        self.assertEqual(record['components'][0]['exclusion_reasons'], ['boundary_contact'])
        self.assertEqual(record['components'][2]['exclusion_reasons'], ['below_minimum_area'])
        packet = component_packet(bundle, min_area_pixels=2, boundary_filter='interior')
        files = self.files(packet)
        self.assertEqual(files['evidence.zip'], bundle)
        with Image.open(io.BytesIO(files['selection.png'])) as selection:
            selected_points = {(x, y) for y in range(8) for x in range(8) if selection.getpixel((x, y))}
        self.assertEqual(selected_points, {(2, 2), (3, 3)})
        self.assertEqual(hashlib.sha256(bundle).hexdigest(), original_sha)
        self.assertEqual(verify_component_packet(packet)['selected_foreground_pixels'], 2)

    def test_roi_boundary_is_geometric_not_an_out_of_image_neighbor(self):
        roi = {'xyxy': [1, 1, 6, 6], 'source': 'imported', 'image_size': [8, 8]}
        record = inspect_components(self.bundle([(x, 3) for x in range(8)], roi=roi))
        item = record['components'][0]
        self.assertEqual(item['area_pixels'], 5)
        self.assertEqual(item['bbox'], [1, 3, 6, 4])
        self.assertTrue(item['touches_roi_boundary'])
        self.assertFalse(item['touches_image_boundary'])
        self.assertFalse(item['touches_invalid_boundary'])
        edge = inspect_components(self.bundle([(0, 0)]))['components'][0]
        self.assertTrue(edge['touches_image_boundary'])
        self.assertFalse(edge['touches_roi_boundary'])

    def test_validity_hole_splits_source_component_and_flags_both_fragments(self):
        bundle = self.bundle([(x, 3) for x in range(1, 6)], invalid=[(3, 3)])
        record = inspect_components(bundle)
        self.assertEqual(record['component_count'], 2)
        self.assertEqual(record['foreground_pixels'], 4)
        self.assertEqual([item['bbox'] for item in record['components']], [[1, 3, 3, 4], [4, 3, 6, 4]])
        for item in record['components']:
            self.assertTrue(item['touches_invalid_boundary'])
            self.assertFalse(item['touches_image_boundary'])
            self.assertFalse(item['touches_roi_boundary'])
        _, files = load_verified_bundle(bundle)
        with Image.open(io.BytesIO(files['full_mask.png'])) as original:
            self.assertEqual(original.histogram()[255], 5)

    def test_diagonal_invalid_neighbor_counts_and_boundary_flags_can_overlap(self):
        roi = {'xyxy': [2, 2, 5, 5], 'source': 'imported', 'image_size': [8, 8]}
        item = inspect_components(self.bundle([(2, 2)], invalid=[(1, 1)], roi=roi))['components'][0]
        self.assertTrue(item['touches_invalid_boundary'])
        self.assertTrue(item['touches_roi_boundary'])
        self.assertFalse(item['touches_image_boundary'])
        item = inspect_components(self.bundle([(2, 2)], invalid=[(3, 3)]))['components'][0]
        self.assertTrue(item['touches_invalid_boundary'])

    def test_touching_selection_uses_union_of_three_independent_flags(self):
        points = [(0, 1), (2, 4), (4, 4)]
        bundle = self.bundle(points, invalid=[(5, 5)])
        record = inspect_components(bundle, boundary_filter='touching')
        self.assertEqual([item['component_id'] for item in record['components'] if item['selected']], [1, 3])
        self.assertEqual(record['selected_foreground_pixels'], 2)

    def test_empty_mask_and_empty_valid_domain_are_replayable(self):
        for bundle in (self.bundle([]), self.bundle([(2, 2)], invalid=[(x, y) for x in range(8) for y in range(8)])):
            with self.subTest(bundle_sha=hashlib.sha256(bundle).hexdigest()):
                record = inspect_components(bundle)
                self.assertEqual(record['components'], [])
                self.assertEqual(record['component_count'], 0)
                self.assertEqual(record['selected_foreground_pixels'], 0)
                self.assertTrue(verify_component_packet(component_packet(bundle))['verified'])

    def test_complement_is_inspected_only_within_valid_analysis_domain(self):
        bundle = self.bundle([(2, 2)], size=(4, 4), invalid=[(0, y) for y in range(4)], invert=True)
        record = inspect_components(bundle)
        self.assertEqual(record['foreground_pixels'], 11)
        self.assertEqual(record['component_count'], 1)
        self.assertTrue(record['components'][0]['touches_invalid_boundary'])

    def test_bad_options_and_explicit_resource_bound_are_rejected(self):
        bundle = self.bundle([(0, 0), (4, 4)])
        for minimum in (0, -1, True, 1.5, '2'):
            with self.subTest(minimum=minimum), self.assertRaises(ValueError):
                inspect_components(bundle, min_area_pixels=minimum)
        with self.assertRaises(ValueError):
            inspect_components(bundle, boundary_filter='unknown')
        with patch('geomasklab.components.MAX_COMPONENTS', 1), self.assertRaisesRegex(ValueError, 'component limit'):
            inspect_components(bundle)

    def test_component_record_tampering_with_updated_hashes_is_rejected(self):
        packet = component_packet(self.bundle([(0, 0), (4, 4)]))
        original_files = self.files(packet)
        for field, value in [('area_pixels', 22), ('bbox', [0, 0, 8, 8]), ('touches_image_boundary', False),
                             ('selected', False), ('component_id', 9), ('centroid', {'x': 9.5, 'y': 2.5})]:
            files = deepcopy(original_files)
            record = json.loads(files['inspection.json'])
            record['components'][0][field] = value
            files['inspection.json'] = json.dumps(record).encode()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'do not replay'):
                verify_component_packet(self.rehash(files))

    def test_record_type_tampering_is_rejected_even_when_python_boolean_equals_int(self):
        files = self.files(component_packet(self.bundle([(0, 0)])))
        record = json.loads(files['inspection.json'])
        record['components'][0]['area_pixels'] = True
        files['inspection.json'] = json.dumps(record).encode()
        with self.assertRaises(ValueError):
            verify_component_packet(self.rehash(files))

    def test_rehashed_selection_csv_report_and_source_replacement_are_rejected(self):
        original = self.files(component_packet(self.bundle([(1, 1)])))
        replacements = {'selection.png': png(Image.new('L', (8, 8), 255)),
                        'components.csv': b'Invented component table\n', 'report.md': b'Invented inspection report\n',
                        'evidence.zip': self.bundle([(4, 4)])}
        for name, raw in replacements.items():
            files = deepcopy(original)
            files[name] = raw
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify_component_packet(self.rehash(files))

    def test_extra_member_nonflat_path_duplicate_and_missing_file_are_rejected(self):
        original = self.files(component_packet(self.bundle([(1, 1)])))
        for name in ('extra.txt', '../escape.txt'):
            files = deepcopy(original)
            files[name] = b'Unexpected'
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify_component_packet(self.rehash(files))
        files = deepcopy(original)
        del files['selection.png']
        with self.assertRaises(ValueError):
            verify_component_packet(self.rehash(files))
        packet = self.rehash(original)
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            names = archive.namelist()
            copied = [(name, archive.read(name)) for name in names]
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, raw in copied:
                archive.writestr(name, raw)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr('inspection.json', b'Duplicate member trap')
        with self.assertRaises(ValueError):
            verify_component_packet(output.getvalue())

    def test_rehash_without_actual_sha_preserves_rejection(self):
        files = self.files(component_packet(self.bundle([(1, 1)])))
        payload = self.rehash(files)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        manifest['checksums']['components.csv']['bytes'] += 1
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)
            archive.writestr('manifest.json', json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            verify_component_packet(output.getvalue())

    def test_randomized_components_match_independent_union_find_and_set_domains(self):
        rng = random.Random(7014)
        width, height = 7, 6
        whole = {(x, y) for y in range(height) for x in range(width)}
        for trial in range(80):
            points = {p for p in sorted(whole) if rng.random() < .32}
            invalid = {p for p in sorted(whole) if rng.random() < .12} or {(0, 0)}
            scope = rng.choice(['all', 'left', 'right', 'top', 'bottom'])
            roi = None
            boxes = {'all': (0, 0, width, height), 'left': (0, 0, width // 2, height),
                     'right': (width // 2, 0, width, height), 'top': (0, 0, width, height // 2),
                     'bottom': (0, height // 2, width, height)}
            x1, y1, x2, y2 = boxes[scope]
            if scope == 'all' and trial % 2:
                roi = {'xyxy': [1, 1, 6, 5], 'source': 'imported', 'image_size': [width, height]}
                x1, y1, x2, y2 = roi['xyxy']
            geometric = {(x, y) for x, y in whole if x1 <= x < x2 and y1 <= y < y2}
            invert = trial % 3 == 0
            foreground = ((whole - points) if invert else points) & geometric - invalid
            # A union-find oracle merges only previously encountered neighbors;
            # inspection uses a queue flood-fill and does not supply this oracle.
            parent = {p: p for p in foreground}
            def find(p):
                while parent[p] != p:
                    parent[p] = parent[parent[p]]
                    p = parent[p]
                return p
            for x, y in sorted(foreground, key=lambda p: (p[1], p[0])):
                for neighbor in ((x - 1, y), (x - 1, y - 1), (x, y - 1), (x + 1, y - 1)):
                    if neighbor in foreground:
                        parent[find((x, y))] = find(neighbor)
            groups = {}
            for p in foreground:
                groups.setdefault(find(p), set()).add(p)
            components = sorted(groups.values(), key=lambda group: min(y * width + x for x, y in group))
            minimum = rng.randrange(1, 5)
            boundary_filter = rng.choice(['all', 'touching', 'interior'])
            bundle = self.bundle(points, size=(width, height), invalid=invalid, roi=roi, scope=scope, invert=invert)
            record = inspect_components(bundle, min_area_pixels=minimum, boundary_filter=boundary_filter)
            self.assertEqual(record['component_count'], len(components), trial)
            self.assertEqual(record['foreground_pixels'], len(foreground), trial)
            selected_points = set()
            for expected, actual in zip(components, record['components']):
                image_flag = any(x in (0, width - 1) or y in (0, height - 1) for x, y in expected)
                neighbors = {(x + dx, y + dy) for x, y in expected for dx in (-1, 0, 1)
                             for dy in (-1, 0, 1) if dx or dy} & whole
                roi_flag = bool(neighbors - geometric)
                invalid_flag = bool(neighbors & invalid)
                touching = image_flag or roi_flag or invalid_flag
                selected = len(expected) >= minimum and (boundary_filter == 'all' or
                            (boundary_filter == 'touching' and touching) or
                            (boundary_filter == 'interior' and not touching))
                self.assertEqual(actual['area_pixels'], len(expected), trial)
                self.assertEqual(actual['bbox'], [min(x for x, y in expected), min(y for x, y in expected),
                                                 max(x for x, y in expected) + 1, max(y for x, y in expected) + 1], trial)
                self.assertEqual(actual['centroid'], {'x': round(sum(x + .5 for x, y in expected) / len(expected), 6),
                                                     'y': round(sum(y + .5 for x, y in expected) / len(expected), 6)}, trial)
                self.assertEqual((actual['touches_image_boundary'], actual['touches_roi_boundary'],
                                  actual['touches_invalid_boundary']), (image_flag, roi_flag, invalid_flag), trial)
                self.assertEqual(actual['selected'], selected, trial)
                if selected:
                    selected_points |= expected
            self.assertEqual(record['selected_foreground_pixels'], len(selected_points), trial)
            files = self.files(component_packet(bundle, min_area_pixels=minimum, boundary_filter=boundary_filter))
            with Image.open(io.BytesIO(files['selection.png'])) as selection:
                actual_points = {(x, y) for x, y in whole if selection.getpixel((x, y))}
            self.assertEqual(actual_points, selected_points, trial)

    @unittest.skipUnless(importlib.util.find_spec('jsonschema'), 'Optional jsonschema dependency is not installed.')
    def test_formal_record_and_manifest_schemas_cover_exported_packet(self):
        from jsonschema import Draft202012Validator
        folder = Path(__file__).resolve().parents[1] / 'src' / 'geomasklab' / 'schemas'
        packet = component_packet(self.bundle([(0, 0), (4, 4)], invalid=[(5, 5)]), boundary_filter='touching')
        with zipfile.ZipFile(io.BytesIO(packet)) as archive:
            inspection = json.loads(archive.read('inspection.json'))
            manifest = json.loads(archive.read('manifest.json'))
        for filename, obj in [('components-1.0.schema.json', inspection), ('component-packet-1.0.schema.json', manifest)]:
            schema = json.loads((folder / filename).read_text(encoding='utf-8'))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(obj)

    def test_operation_version_is_a_bounded_portable_token(self):
        original = self.files(component_packet(self.bundle([(1, 1)])))
        for value in ('two words', '\u6d4b\u8bd5', '', 'v' * 65, '1.0\n'):
            with self.subTest(value=value):
                content = dict(original)
                record = json.loads(content['inspection.json'])
                record['software_version'] = value
                content['inspection.json'] = json.dumps(record).encode()
                with self.assertRaisesRegex(ValueError, 'software version'):
                    verify_component_packet(self.rehash(content))


if __name__ == '__main__':
    unittest.main()
