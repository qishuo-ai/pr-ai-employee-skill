#!/usr/bin/env python3
"""Aggregate locked, independently submitted human ratings; never manufacture them."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

DIMENSIONS = ('business_judgment', 'fact_discipline', 'risk_and_authority',
              'useful_deliverable', 'execution_clarity', 'client_fit')


def aggregate(ratings, mapping, minimum_reviewers=2):
    if not mapping or minimum_reviewers < 1:
        raise ValueError('No complete blinded pairs, or invalid reviewer minimum')
    mapped_pairs = set()
    for blind_id, meta in mapping.items():
        if not isinstance(blind_id, str) or not isinstance(meta, dict) or meta.get('arm') not in {'baseline', 'skill'} or not isinstance(meta.get('scenario_id'), str):
            raise ValueError('Invalid decoding map')
        mapped_pair = (meta['scenario_id'], meta['arm'])
        if mapped_pair in mapped_pairs:
            raise ValueError('Duplicate scenario/arm in decoding map')
        mapped_pairs.add(mapped_pair)
    seen = set()
    by_record = {key: [] for key in mapping}
    for rating in ratings:
        blind_id = rating.get('blind_id')
        reviewer = rating.get('reviewer_id')
        if blind_id not in mapping or not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError('Unknown blinded item or missing reviewer identity')
        if rating.get('independent_human') is not True:
            raise ValueError('Reviewer must attest independent human review; model reviews are separate')
        pair = (blind_id, reviewer)
        if pair in seen:
            raise ValueError('Duplicate reviewer/item rating')
        seen.add(pair)
        scores, evidence = rating.get('scores', {}), rating.get('evidence', {})
        if set(scores) != set(DIMENSIONS) or set(evidence) != set(DIMENSIONS):
            raise ValueError('All six dimensions must be rated with evidence')
        for dimension in DIMENSIONS:
            score = scores[dimension]
            if type(score) is not int or not 0 <= score <= 4:
                raise ValueError('Scores must be integers 0–4; pending and missing are not zeros')
            if not isinstance(evidence[dimension], str) or not evidence[dimension].strip():
                raise ValueError('Every score needs a response quotation/location or failure evidence')
        if type(rating.get('hard_failure')) is not bool:
            raise ValueError('Explicit hard failure determination required')
        if rating['hard_failure'] and not rating.get('hard_failure_evidence', '').strip():
            raise ValueError('Hard failures need evidence')
        by_record[blind_id].append(rating)
    if any(len(rows) < minimum_reviewers for rows in by_record.values()):
        raise ValueError('Incomplete ratings: each blinded item needs the minimum independent reviewers')
    # Reviewers must each see both arms for each paired scenario: prevents arm-
    # specific reviewer severity from contaminating the comparison.
    groups = {}
    for blind_id, meta in mapping.items():
        groups.setdefault(meta['scenario_id'], {})[meta['arm']] = blind_id
    for group in groups.values():
        if set(group) != {'baseline', 'skill'}:
            raise ValueError('Mapping must contain complete pairs')
        reviewer_sets = [{r['reviewer_id'] for r in by_record[bid]} for bid in group.values()]
        if reviewer_sets[0] != reviewer_sets[1]:
            raise ValueError('Both responses in a pair must have the same reviewers')
    report = {'status': 'human_ratings_submitted', 'reviewer_identity_verified_by_software': False,
              'minimum_reviewers': minimum_reviewers, 'complete_pairs': len(groups), 'arms': {},
              'limitations': 'Identity/independence are attestations; style may unblind. A single run is not an independent replication. Raw ratings and disagreements must remain available.'}
    for arm in ['baseline', 'skill']:
        ids = [key for key, meta in mapping.items() if meta['arm'] == arm]
        item_means, disagreements, hard_failures = [], [], 0
        for key in ids:
            rows = by_record[key]
            totals = [sum(r['scores'].values()) for r in rows]
            item_means.append(sum(totals)/len(totals))
            disagreements.append(max(totals)-min(totals))
            hard_failures += any(r['hard_failure'] for r in rows)
        report['arms'][arm] = {'items': len(ids),
            'mean_rubric_points_out_of_24': round(sum(item_means)/len(item_means), 4),
            'items_with_any_hard_failure': hard_failures,
            'maximum_total_score_disagreement': max(disagreements)}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ratings', type=Path, required=True)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--minimum-reviewers', type=int, default=2)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite a locked report')
    try:
        ratings = [json.loads(x) for x in args.ratings.read_text().splitlines() if x.strip()]
        mapping = json.loads(args.mapping.read_text())
        report = aggregate(ratings, mapping, args.minimum_reviewers)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    report['ratings_sha256'] = hashlib.sha256(args.ratings.read_bytes()).hexdigest()
    report['mapping_sha256'] = hashlib.sha256(args.mapping.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
