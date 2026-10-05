"""Product boundaries, independent of planner/model performance claims."""
from copy import deepcopy

VERSION = '0.9.0-dev.2'
TARGET_CAPABILITIES = {
    'building': {'label': '建筑', 'level': 'primary', 'evidence': 'limited_prior_version_application_study'},
    'aircraft': {'label': '飞机', 'level': 'primary', 'evidence': 'limited_prior_version_application_study'},
    'road': {'label': '道路', 'level': 'experimental', 'evidence': 'no_frozen_semantic_evaluation'},
    'water': {'label': '水体', 'level': 'experimental', 'evidence': 'no_frozen_semantic_evaluation'},
    'tree': {'label': '植被', 'level': 'experimental', 'evidence': 'no_frozen_semantic_evaluation'},
    'ship': {'label': '船舶', 'level': 'experimental', 'evidence': 'no_frozen_semantic_evaluation'},
}

def capabilities():
    return {'schema': 'geoscope-product/0.1', 'version': VERSION,
            'profile': 'assisted_pixel_segmentation',
            'targets': deepcopy(TARGET_CAPABILITIES),
            'primary_targets': ['building', 'aircraft'],
            'scopes': ['whole', 'pixel_half', 'rectangle_roi'],
            'measurements': ['foreground_pixels', 'whole_image_coverage', 'candidate_components'],
            'semantic_review_required': True, 'geographic_area_available': False,
            'quality_mode_accuracy_guaranteed': False,
            'prior_evaluation_commit': '46ffbbb1898a4b5e8f2ac5974f0bdabace3a94bd',
            'release_status': 'development; installation, interaction and model-quality acceptance pending'}
