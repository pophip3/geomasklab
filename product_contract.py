"""Product boundaries, independent of planner/model performance claims."""
from copy import deepcopy

VERSION = '1.0.0-dev.5'
PRODUCT_NAME = 'GeoMaskLab'
TARGET_CAPABILITIES = {
    'building': {'label': 'Buildings', 'level': 'primary', 'evidence': 'limited_prior_version_application_study'},
    'aircraft': {'label': 'Aircraft', 'level': 'primary', 'evidence': 'limited_prior_version_application_study'},
    'road': {'label': 'Roads', 'level': 'experimental', 'evidence': 'no_frozen_semantic_evaluation'},
    'water': {'label': 'Water', 'level': 'experimental', 'evidence': 'no_frozen_semantic_evaluation'},
    'tree': {'label': 'Vegetation', 'level': 'experimental', 'evidence': 'no_frozen_semantic_evaluation'},
    'ship': {'label': 'Ships', 'level': 'experimental', 'evidence': 'no_frozen_semantic_evaluation'},
}

def capabilities():
    return {'schema': 'geoscope-product/0.1', 'version': VERSION, 'name': PRODUCT_NAME,
            'profile': 'assisted_pixel_segmentation',
            'targets': deepcopy(TARGET_CAPABILITIES),
            'primary_targets': ['building', 'aircraft'],
            'scopes': ['whole', 'pixel_half', 'rectangle_roi'],
            'measurements': ['foreground_pixels', 'whole_image_coverage', 'within_region_coverage', 'candidate_components'],
            'offline_operations': ['verify_evidence', 'import_evidence', 'semantic_review', 'saved_mask_region_analysis',
                                   'result_comparison', 'experiment_library', 'measurement_ledger',
                                   'external_mask_import', 'reference_evaluation'],
            'interface': 'local_browser_workbench',
            'scope_definition': 'docs/software_scope.md',
            'semantic_review_required': True, 'geographic_area_available': False,
            'quality_mode_accuracy_guaranteed': False,
            'prior_evaluation_commit': '46ffbbb1898a4b5e8f2ac5974f0bdabace3a94bd',
            'release_status': 'version 1.0 functional scope defined; software acceptance in progress'}
