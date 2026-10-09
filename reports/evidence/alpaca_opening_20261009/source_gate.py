"""Fail-closed operator companion guard, not an authenticator or money authority.

A source-hash declaration cannot independently prove completeness/authenticity.
The operator must separately inspect the declared sources before writing a
VERIFIED review. Broker protection acceptance remains a subsequent PAPER gate.
"""
import hashlib,json,re

def require_review(review,archive_sha256,now_ms):
    if review is None:raise ValueError('OPENING_SOURCE_REVIEW_MISSING')
    try:
        if (review['schema']!='ALPACA_OPENING_OPERATOR_SOURCE_REVIEW_V1'
            or type(review['observed_ms']) is not int or type(now_ms) is not int
            or not 0<=now_ms-review['observed_ms']<=300000
            or review['initial_archive_sha256']!=archive_sha256
            or review['broker_authenticated_by_this_validator'] is not False):
            raise ValueError('OPENING_SOURCE_REVIEW_BINDING')
        owner=review['owner'];protection=review['protection']
        if owner['status']!='VERIFIED' or owner['all_installed_writers_reviewed'] is not True:
            raise ValueError('OWNER_SOURCE_REVIEW')
        if (protection['status']!='PAPER_PROTOCOL_ELIGIBILITY_ONLY'
            or protection['actual_acceptance_proven'] is not False):
            raise ValueError('PROTECTION_ELIGIBILITY_ONLY')
        for pin in [archive_sha256,*[review[k]['source_sha256'] for k in ['owner','protection','earnings','cost']]]:
            if not isinstance(pin,str) or not re.fullmatch('[0-9a-f]{64}',pin):
                raise ValueError('OPENING_SOURCE_REVIEW_PIN')
        raw=json.dumps(review,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        return {'source_sha256':hashlib.sha256(raw).hexdigest(),'money_authority':False,
                'broker_truth_authenticated':False,'evidence_kind':'OPERATOR_INPUT_PROVIDED'}
    except (KeyError,TypeError):raise ValueError('OPENING_SOURCE_REVIEW_INCOMPLETE') from None
