"""Independent set arithmetic and hostile-packet checks for fair comparison."""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import _source_package
_source_package.use_local_core()
from PIL import Image, PngImagePlugin
from geomasklab.api import create_evidence
from geomasklab import comparison
from geomasklab.comparison import compare_bundles, comparison_packet, verify_comparison_packet


SIZE = (5, 3)
PIXELS = set(range(15))


def binary(pixels, *, foreground=255):
    """Encode a hand-defined set of row-major pixel indices."""
    image = Image.new('L', SIZE)
    for index in pixels:
        image.putpixel((index % SIZE[0], index // SIZE[0]), foreground)
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def members(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def rehash_packet(content):
    """Rebuild every digest, so replay rather than hashing detects the lie."""
    content = dict(content)
    content.pop('manifest.json', None)
    manifest = {'schema': comparison.PACKET_SCHEMA, 'checksums': {
        name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        for name, raw in content.items()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in content.items():
            archive.writestr(name, raw)
        archive.writestr('manifest.json', json.dumps(manifest))
    return output.getvalue()


class FairComparison(unittest.TestCase):
    def setUp(self):
        output = io.BytesIO()
        Image.new('RGB', SIZE, (17, 31, 47)).save(output, 'PNG')
        self.image = output.getvalue()

    def create(self, foreground, *, valid=None, image=None, **options):
        if valid is not None:
            options.update(valid_mask=binary(valid), valid_source='Hand-defined validity fixture.')
        return create_evidence(image or self.image, binary(foreground),
            target=options.pop('target', 'building'), source='Hand-defined source fixture.',
            aligned=True, **options)

    def pair(self):
        # Left half excludes index 5: D_A={0,1,6,10,11}. Top half:
        # D_B={0,1,2,3,4}. Their common domain is exactly {0,1}.
        return (self.create({0, 6, 11}, scope='left', valid=PIXELS - {5}),
                self.create({1, 2, 3, 4}, scope='top'))

    def test_hand_defined_common_domain_and_total_accounting(self):
        result = compare_bundles(*self.pair())
        expected = {'common_scope_pixels': 2, 'a_domain_pixels': 5, 'b_domain_pixels': 5,
            'a_foreground_in_common_scope': 1, 'b_foreground_in_common_scope': 1,
            'shared_foreground_pixels': 0, 'a_only_pixels': 1, 'b_only_pixels': 1,
            'changed_pixels': 2, 'a_domain_excluded_from_comparison_pixels': 3,
            'b_domain_excluded_from_comparison_pixels': 3}
        for name, value in expected.items():
            self.assertEqual(result[name], value, name)
        self.assertEqual((result['a']['foreground_pixels'], result['b']['foreground_pixels']), (3, 4))
        self.assertEqual(result['a']['foreground_excluded_from_comparison_pixels'], 2)
        self.assertEqual(result['b']['foreground_excluded_from_comparison_pixels'], 3)
        self.assertEqual(result['foreground_change_accounting']['saved_total_delta_pixels'], 1)
        self.assertEqual(result['foreground_change_accounting']['common_domain_delta_pixels'], 0)
        self.assertEqual(result['foreground_change_accounting']['excluded_domain_delta_pixels'], 1)
        self.assertFalse(result['foreground_change_accounting']['causal_attribution'])
        self.assertEqual(result['mask_agreement_iou'], 0)
        self.assertEqual(result['mask_agreement_dice'], 0)
        self.assertEqual(result['change_kind'], 'Prediction_And_Analysis_Conditions')

    def test_swap_reverses_direction_but_preserves_agreement(self):
        a = self.create({0, 1, 3})
        b = self.create({1, 2})
        ab, ba = compare_bundles(a, b), compare_bundles(b, a)
        self.assertEqual((ab['a_only_pixels'], ab['b_only_pixels']), (2, 1))
        self.assertEqual((ba['a_only_pixels'], ba['b_only_pixels']), (1, 2))
        for key in ('mask_agreement_iou', 'mask_agreement_dice', 'changed_pixels', 'shared_foreground_pixels'):
            self.assertEqual(ab[key], ba[key], key)
        for key in ('saved_total_delta_pixels', 'common_domain_delta_pixels', 'excluded_domain_delta_pixels'):
            self.assertEqual(ab['foreground_change_accounting'][key], -ba['foreground_change_accounting'][key])
        self.assertEqual(ab['a'], ba['b'])
        self.assertEqual(ab['b'], ba['a'])

    def test_scope_changes_do_not_masquerade_as_prediction_changes(self):
        source = {0, 1, 2, 3, 4, 6, 11}
        result = compare_bundles(self.create(source, scope='left', valid=PIXELS - {5}),
                                 self.create(source, scope='top'))
        self.assertEqual(result['change_kind'], 'Analysis_Conditions_Only')
        self.assertTrue(result['full_prediction_pixels_equal'])
        self.assertEqual(result['changed_pixels'], 0)
        self.assertEqual(result['mask_agreement_iou'], 1)
        self.assertEqual(result['foreground_change_accounting']['saved_total_delta_pixels'], 1)
        self.assertEqual(result['foreground_change_accounting']['common_domain_delta_pixels'], 0)
        self.assertEqual(result['foreground_change_accounting']['excluded_domain_delta_pixels'], 1)

    def test_prediction_changes_outside_common_domain_are_reported_separately(self):
        a = self.create({0, 1, 6}, scope='left')
        b = self.create({0, 1, 2, 4}, scope='top')
        result = compare_bundles(a, b)
        self.assertFalse(result['full_prediction_pixels_equal'])
        self.assertEqual(result['changed_pixels'], 0)
        self.assertEqual(result['mask_agreement_iou'], 1)
        self.assertIn('outside the common valid domain', result['explanation'])

    def test_matching_conditions_is_prediction_only(self):
        result = compare_bundles(self.create({0, 1}), self.create({1, 2, 4}))
        self.assertEqual(result['change_kind'], 'Prediction_Only')
        self.assertEqual(result['mask_agreement_iou'], 1 / 4)
        self.assertEqual(result['mask_agreement_dice'], 2 / 5)

    def test_identical_policy_checks_realized_domain_not_global_validity(self):
        source = {0, 1, 2, 6}
        a = self.create(source, scope='left', valid=PIXELS)
        b = self.create(source, scope='left', valid=PIXELS - {2, 3, 4, 7, 8, 9})
        result = compare_bundles(a, b, domain_policy='identical')
        self.assertTrue(result['selected_valid_domains_equal'])
        self.assertFalse(result['valid_masks_equal'])
        self.assertEqual(result['common_scope_pixels'], 6)
        self.assertEqual(result['changed_pixels'], 0)
        self.assertIn('outside that effective domain', result['explanation'])

    def test_full_image_rectangle_matches_realized_all_scope(self):
        roi = {'xyxy': [0, 0, 5, 3], 'source': 'imported', 'image_size': [5, 3]}
        result = compare_bundles(self.create({1, 6}), self.create({1, 6}, roi=roi), domain_policy='identical')
        self.assertTrue(result['selected_regions_equal'])
        self.assertEqual(result['change_kind'], 'Identical_Realized_Analysis')
        self.assertEqual(result['a']['roi'], None)
        self.assertEqual(result['b']['roi'], roi)

    def test_different_binary_upload_encodings_have_equal_prediction_pixels(self):
        a = self.create({0, 1})
        b = create_evidence(self.image, binary({0, 1}, foreground=1), target='building',
                            source='Lossless 0/1 binary encoding fixture.', aligned=True)
        result = compare_bundles(a, b)
        self.assertTrue(result['full_prediction_pixels_equal'])
        self.assertEqual(result['change_kind'], 'Identical_Realized_Analysis')
        self.assertNotEqual(result['source_a_sha256'], result['source_b_sha256'])

    def test_strict_domain_mismatch_requires_explicit_intersection(self):
        a, b = self.pair()
        with self.assertRaisesRegex(ValueError, 'Incompatible_Analysis_Domains'):
            compare_bundles(a, b, domain_policy='identical')
        self.assertEqual(compare_bundles(a, b, domain_policy='intersection')['common_scope_pixels'], 2)
        with self.assertRaisesRegex(ValueError, 'domain policy'):
            compare_bundles(a, b, domain_policy='automatic')

    def test_empty_common_domain_has_no_diff_or_agreement(self):
        a = self.create({0, 1}, valid={0, 1})
        b = self.create({1, 2}, valid={2, 3})
        result = compare_bundles(a, b)
        self.assertEqual(result['status'], 'No_Common_Valid_Domain')
        self.assertFalse(result['pixel_diff_available'])
        for key in ('mask_agreement_iou', 'mask_agreement_dice', 'difference_png_base64', 'difference_classes_png_base64'):
            self.assertIsNone(result[key], key)
        packet = comparison_packet(a, b)
        self.assertEqual(set(members(packet)), {'source-a.zip', 'source-b.zip', 'comparison.json', 'report.html', 'manifest.json'})
        self.assertTrue(verify_comparison_packet(packet)['verified'])

    def test_equal_empty_domains_are_admitted_but_not_scored(self):
        a = self.create({0}, valid=set())
        b = self.create({1}, valid=set())
        result = compare_bundles(a, b, domain_policy='identical')
        self.assertEqual(result['status'], 'No_Common_Valid_Domain')
        self.assertTrue(result['selected_valid_domains_equal'])
        self.assertIsNone(result['a']['coverage_of_valid_region'])
        self.assertIsNone(result['b']['coverage_of_valid_region'])

    def test_nonempty_domain_with_empty_union_has_undefined_agreement(self):
        result = compare_bundles(self.create(set()), self.create(set()))
        self.assertEqual(result['status'], 'Compared')
        self.assertTrue(result['pixel_diff_available'])
        self.assertEqual(result['common_scope_pixels'], 15)
        self.assertIsNone(result['mask_agreement_iou'])
        self.assertIsNone(result['mask_agreement_dice'])
        classes = Image.open(io.BytesIO(base64.b64decode(result['difference_classes_png_base64'])))
        self.assertEqual(set(classes.tobytes()), {1})

    def test_complements_are_only_compared_inside_valid_pixels(self):
        result = compare_bundles(self.create({0}, valid={0, 1, 2}, invert=True),
                                 self.create({1, 2}, valid={0, 1, 2}, invert=True))
        self.assertEqual(result['common_scope_pixels'], 3)
        self.assertEqual((result['a_only_pixels'], result['b_only_pixels'], result['shared_foreground_pixels']), (2, 1, 0))
        self.assertEqual((result['a']['foreground_pixels'], result['b']['foreground_pixels']), (2, 1))
        classes = Image.open(io.BytesIO(base64.b64decode(result['difference_classes_png_base64'])))
        for index in PIXELS - {0, 1, 2}:
            self.assertEqual(classes.getpixel((index % 5, index // 5)), 0)

    def test_semantic_and_exact_image_admission_guards(self):
        a = self.create({0})
        for b in (self.create({0}, target='vegetation'), self.create({0}, invert=True)):
            with self.assertRaisesRegex(ValueError, 'same semantic target'):
                compare_bundles(a, b)
        # Identical pixels with different PNG metadata still have different exact
        # input identities. Equal dimensions are never a registration assertion.
        info = PngImagePlugin.PngInfo()
        info.add_text('Source', 'A different exact source asset.')
        output = io.BytesIO()
        Image.new('RGB', SIZE, (17, 31, 47)).save(output, 'PNG', pnginfo=info)
        with self.assertRaisesRegex(ValueError, 'same exact input image'):
            compare_bundles(a, self.create({0}, image=output.getvalue()))

    def test_categorical_difference_has_named_pixel_states(self):
        result = compare_bundles(self.create({0, 1}), self.create({1, 2}))
        classes = Image.open(io.BytesIO(base64.b64decode(result['difference_classes_png_base64'])))
        self.assertEqual(classes.mode, 'L')
        self.assertEqual(classes.size, SIZE)
        self.assertEqual([classes.getpixel((x, 0)) for x in range(5)], [3, 2, 4, 1, 1])
        overlay = Image.open(io.BytesIO(base64.b64decode(result['difference_png_base64'])))
        self.assertEqual(overlay.mode, 'RGB')
        self.assertEqual(overlay.size, SIZE)

    def test_packet_replays_both_exact_sources_and_reports_boundary(self):
        a, b = self.pair()
        payload = comparison_packet(a, b)
        content = members(payload)
        self.assertEqual(content['source-a.zip'], a)
        self.assertEqual(content['source-b.zip'], b)
        record = json.loads(content['comparison.json'])
        self.assertNotIn('difference_png_base64', record)
        self.assertNotIn('difference_classes_png_base64', record)
        facts = verify_comparison_packet(payload)
        self.assertTrue(facts['verified'])
        self.assertFalse(facts['origin_authenticated'])
        self.assertFalse(facts['semantic_accuracy_measured'])
        self.assertEqual(facts['comparison'], record)

    def test_rehashed_false_record_and_boolean_integer_are_rejected(self):
        content = members(comparison_packet(*self.pair()))
        for field, value in [('a_only_pixels', 17), ('a_foreground_in_common_scope', True), ('selected_valid_domains_equal', 0)]:
            changed = dict(content)
            record = json.loads(changed['comparison.json'])
            record[field] = value
            changed['comparison.json'] = json.dumps(record).encode()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'record disagrees'):
                verify_comparison_packet(rehash_packet(changed))

    def test_rehashed_pixel_changes_and_wrong_modes_are_rejected(self):
        content = members(comparison_packet(*self.pair()))
        for name, mode in [('difference-classes.png', None), ('difference.png', 'L')]:
            changed = dict(content)
            image = Image.open(io.BytesIO(changed[name]))
            if mode:
                image = image.convert(mode)
            else:
                image.putpixel((0, 0), 1)
            output = io.BytesIO()
            image.save(output, 'PNG')
            changed[name] = output.getvalue()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'image disagrees'):
                verify_comparison_packet(rehash_packet(changed))

    def test_rehashed_report_and_swapped_sources_are_rejected(self):
        content = members(comparison_packet(*self.pair()))
        changed = {**content, 'report.html': content['report.html'] + b'<p>False extra conclusion.</p>'}
        with self.assertRaisesRegex(ValueError, 'report disagrees'):
            verify_comparison_packet(rehash_packet(changed))
        changed = {**content, 'source-a.zip': content['source-b.zip'], 'source-b.zip': content['source-a.zip']}
        with self.assertRaisesRegex(ValueError, 'record disagrees'):
            verify_comparison_packet(rehash_packet(changed))

    def test_flat_membership_and_difference_availability_are_enforced(self):
        content = members(comparison_packet(*self.pair()))
        for name in ('unexpected.txt', '../comparison.json', 'subfolder/comparison.json'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'membership'):
                verify_comparison_packet(rehash_packet({**content, name: b'Unlisted content.'}))
        without_images = {name: raw for name, raw in content.items() if name not in ('difference.png', 'difference-classes.png')}
        with self.assertRaisesRegex(ValueError, 'availability'):
            verify_comparison_packet(rehash_packet(without_images))

    def test_duplicate_packet_member_is_rejected(self):
        content = members(comparison_packet(*self.pair()))
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, raw in content.items():
                archive.writestr(name, raw)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr('comparison.json', content['comparison.json'])
        with self.assertRaisesRegex(ValueError, 'membership'):
            verify_comparison_packet(output.getvalue())

    def test_new_verifier_preserves_recorded_operation_version(self):
        payload = comparison_packet(*self.pair())
        original = json.loads(members(payload)['comparison.json'])
        self.assertIn('operation_software_version', original)
        self.assertIn('software_version', original['a'])
        self.assertIn('software_version', original['b'])
        with patch.object(comparison, 'VERSION', '1.0.0rc3.dev99'):
            replayed = verify_comparison_packet(payload)['comparison']
        self.assertEqual(replayed['operation_software_version'], original['operation_software_version'])

    def test_operation_version_is_a_bounded_portable_token(self):
        original = members(comparison_packet(*self.pair()))
        for value in ('two words', '\u6d4b\u8bd5', '', 'v' * 65, '1.0\n'):
            with self.subTest(value=value):
                content = dict(original)
                record = json.loads(content['comparison.json'])
                record['operation_software_version'] = value
                content['comparison.json'] = json.dumps(record).encode()
                with self.assertRaisesRegex(ValueError, 'software version'):
                    verify_comparison_packet(rehash_packet(content))

    @unittest.skipUnless(importlib.util.find_spec('jsonschema'), 'Optional JSON Schema validator is unavailable.')
    def test_packaged_schemas_validate_ui_record_persisted_record_and_manifest(self):
        import jsonschema
        folder = Path(comparison.__file__).parent / 'schemas'
        record_schema = json.loads((folder / 'comparison-2.0.schema.json').read_text(encoding='utf-8'))
        packet_schema = json.loads((folder / 'comparison-packet-1.0.schema.json').read_text(encoding='utf-8'))
        jsonschema.Draft202012Validator.check_schema(record_schema)
        jsonschema.Draft202012Validator.check_schema(packet_schema)
        for pair in (self.pair(), (self.create(set(), valid=set()), self.create(set(), valid=set()))):
            record = compare_bundles(*pair)
            jsonschema.validate(record, record_schema)
            content = members(comparison_packet(*pair))
            jsonschema.validate(json.loads(content['comparison.json']), record_schema)
            jsonschema.validate(json.loads(content['manifest.json']), packet_schema)
        bad = deepcopy(compare_bundles(*self.pair()))
        bad['a_foreground_in_common_scope'] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, record_schema)
        bad = deepcopy(compare_bundles(*self.pair()))
        bad['status'] = 'No_Common_Valid_Domain'
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, record_schema)
        bad = deepcopy(compare_bundles(*self.pair()))
        bad.pop('difference_classes_png_base64')
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, record_schema)
        bad = deepcopy(compare_bundles(*self.pair()))
        bad['change_kind'] = 'Prediction_Only'
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, record_schema)
        bad = deepcopy(compare_bundles(self.create(set(), valid=set()), self.create(set(), valid=set())))
        bad['a']['coverage_of_valid_region'] = 0
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, record_schema)
        bad = deepcopy(compare_bundles(*self.pair()))
        bad['mask_agreement_iou'] = None
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, record_schema)
        bad_manifest = json.loads(members(comparison_packet(*self.pair()))['manifest.json'])
        bad_manifest['checksums']['comparison.json']['bytes'] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad_manifest, packet_schema)


if __name__ == '__main__':
    unittest.main()
