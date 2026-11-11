"""Compare named route identities independently of leased HTTP origins.

This operates on a copied semantic view. Full receipts and their hashes remain
in the raw snapshots and are still checked by the source evidence consumer.
"""
import re

from .map_route_normal_capture import fingerprint


def normalize_geocode_receipts(reference, named_evidence):
    """Remove only receipt hashes already bound to complete named evidence.

    Do not recursively discard keys named 'hash': coordinates, OSM identities,
    query strings, full-record hashes, and arbitrary extra fields stay compared.
    """
    endpoints = reference.get('scope', {}).get('geocode_identities')
    if endpoints is None:
        return
    if not isinstance(endpoints, list) or len(endpoints) != 2:
        raise ValueError('Two complete route endpoint identity lists required')
    for identities in endpoints:
        if not isinstance(identities, list) or not identities:
            raise ValueError('Nonempty native endpoint identities required')
        for identity in identities:
            if not isinstance(identity, dict):
                raise ValueError('Complete native endpoint identity required')
            if 'native_receipt_sha256' not in identity:
                # Older snapshots bind the whole identity through the private
                # reference hash, without duplicating its query receipt here.
                # There is no transport field to remove: retain every byte of
                # the identity in the semantic comparison. Do not synthesize a
                # receipt or normalize any coordinates/records to make it pass.
                continue
            query = identity.get('requested_query')
            evidence = named_evidence.get(query) if isinstance(query, str) else None
            receipt = identity.get('native_receipt_sha256')
            record = identity.get('full_geocode_record')
            if (not isinstance(evidence, dict) or evidence.get('query') != query
                    or not re.fullmatch(r'[0-9a-f]{64}', str(receipt))
                    or receipt != evidence.get('native_receipt_sha256')
                    or not isinstance(record, dict)
                    or identity.get('full_geocode_sha256') != fingerprint(record)
                    or record not in evidence.get('full_records', [])):
                raise ValueError('Route identity must bind its complete native query evidence')
            del identity['native_receipt_sha256']
