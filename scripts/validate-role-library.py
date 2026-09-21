#!/usr/bin/env python3
"""Validate role routing, local links and source provenance; not model behavior.

Uses the Python standard library. Optional --upstream checks the reviewed local
source checkout against the manifest without fetching or running its contents.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


def validate(root, upstream=None):
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    def local_file(relative):
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            errors.append(f"Path escapes repository: {relative}")
            return None
        check(path.is_file(), f"Missing file: {relative}")
        return path if path.is_file() else None

    registry = json.loads((root / 'roles/registry.json').read_text(encoding='utf-8'))
    manifest = json.loads((root / 'references/agency-agents-source-manifest.json').read_text(encoding='utf-8'))
    roles = registry['roles']
    ids = [r['id'] for r in roles]
    check(len(ids) == len(set(ids)), 'Duplicate role IDs')
    check(len({r['path'] for r in roles}) == len(roles), 'Duplicate role paths')
    expected_core = {'project-lead', 'strategy-director', 'content-messaging',
                     'project-ops', 'independent-reviewer'}
    check({r['id'] for r in roles if r['kind'] == 'core'} == expected_core,
          'Original core roles must be preserved')
    check(all(r['kind'] in {'core', 'specialist'} for r in roles), 'Unknown role kind')
    check(registry['version'] == (root / 'VERSION').read_text(encoding='utf-8').strip(), 'Version mismatch')
    check(registry['default_mode'] == 'shadow', 'Default mode changed')
    check(registry['runtime'] == 'declarative_only', 'Registry must not imply installed agents')

    sources = manifest['sources']
    by_source = {s['path']: s for s in sources}
    check(len(by_source) == len(sources), 'Duplicate source paths')
    actual_edges = set()
    registered_files = set()
    for role in roles:
        path = local_file(role['path'])
        registered_files.add(role['path'])
        check(bool(role['source_paths']), f"No source mapping: {role['id']}")
        for source in role['source_paths']:
            check(source in by_source, f"Untracked source: {source}")
            actual_edges.add((source, role['path']))
            if path and source in by_source:
                check(by_source[source]['url'] in path.read_text(encoding='utf-8'),
                      f"Source link missing in {role['path']}: {source}")
    on_disk = {p.relative_to(root).as_posix() for p in (root / 'roles').glob('*.md')
               if p.name != 'README.md'}
    check(on_disk == registered_files, 'Role files and registry differ')
    recorded_edges = {(s['path'], target) for s in sources for target in s['adapted_into']}
    check(actual_edges == recorded_edges, 'Source manifest and role mappings differ')
    commit = manifest['commit']
    check(bool(re.fullmatch(r'[0-9a-f]{40}', commit)), 'Source commit is not pinned')
    check(manifest['license'] == 'MIT', 'Unexpected upstream license')
    for source in sources:
        check(source['url'] == f"{manifest['repository']}/blob/{commit}/{source['path']}",
              f"Source URL not pinned: {source['path']}")
        check(bool(re.fullmatch(r'[0-9a-f]{64}', source['sha256'])),
              f"Invalid source hash: {source['path']}")
    license_path = local_file(manifest['license_file'])
    if license_path:
        check(hashlib.sha256(license_path.read_bytes()).hexdigest() == manifest['license_sha256'],
              'Retained upstream license changed')

    recipe_ids = set()
    coverage = set()
    for recipe in registry['recipes']:
        check(recipe['id'] not in recipe_ids, f"Duplicate recipe: {recipe['id']}")
        recipe_ids.add(recipe['id'])
        chosen = [recipe['lead'], *recipe['optional_specialists'], recipe['reviewer']]
        check(all(r in ids for r in chosen), f"Unknown role in recipe: {recipe['id']}")
        check(recipe['reviewer'] == 'independent-reviewer', f"Missing reviewer: {recipe['id']}")
        check(recipe['reviewer'] not in [recipe['lead'], *recipe['optional_specialists']],
              f"Reviewer assigned to production: {recipe['id']}")
        override = recipe.get('single_platform_override', {})
        for specialist in override.get('lead_by_platform', {}).values():
            check(specialist in recipe['optional_specialists'],
                  f"Single-platform lead not in candidate roles: {recipe['id']}")
        coverage.update(recipe['task_types'])
    task_types = {'client_reply', 'strategy', 'proposal', 'content', 'media_kol', 'event',
                  'social', 'project_ops', 'pricing', 'crisis', 'reporting', 'fact_check'}
    check(task_types <= coverage, 'Existing task types missing routing coverage')

    # Check explicit Markdown file links, excluding fenced examples and anchors.
    for path in root.rglob('*.md'):
        if '.git' in path.relative_to(root).parts:
            continue
        text = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.S)
        for target in re.findall(r'\]\(([^)]+)\)', text):
            target = target.strip().strip('<>')
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('#'):
                continue
            target = unquote(target.split('#')[0])
            check((path.parent / target).exists(), f"Broken link: {path.relative_to(root)} → {target}")

    eval_ids = set()
    for path in sorted((root / 'evals').glob('*.jsonl')):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            case = json.loads(line)
            check(case['id'] not in eval_ids, f"Duplicate eval ID: {case['id']}")
            eval_ids.add(case['id'])
            check(bool(case['scenario']) and bool(case['must']), f"Empty eval: {path.name}:{number}")
            check(all(r in ids for r in case.get('expected_roles', [])), f"Unknown eval role: {case['id']}")
    check({f'E{i:02}' for i in range(1, 11)} <= eval_ids, 'Original evals are missing')

    if upstream:
        observed = subprocess.run(['git', '-C', str(upstream), 'rev-parse', 'HEAD'],
                                  capture_output=True, text=True, check=True).stdout.strip()
        check(observed == commit, 'Upstream checkout revision differs from manifest')
        for source in sources:
            path = (upstream / source['path']).resolve()
            check(path.is_relative_to(upstream.resolve()), f"Unsafe source path: {source['path']}")
            if path.is_relative_to(upstream.resolve()) and path.is_file():
                check(hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256'],
                      f"Source hash mismatch: {source['path']}")
            else:
                errors.append(f"Missing source file: {source['path']}")
        check(hashlib.sha256((upstream / 'LICENSE').read_bytes()).hexdigest() == manifest['license_sha256'],
              'Source license differs from retained license')
    return errors, len(roles), len(sources), len(eval_ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        errors, roles, sources, evals = validate(root, args.upstream)
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'FAIL: {exc}')
        return 1
    for error in errors:
        print(f'FAIL: {error}')
    if errors:
        return 1
    print(f'PASS: {roles} roles, {sources} source files, {evals} eval cases; links and routing valid.')
    print('Model behavior and platform execution are not tested by this structural check.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
