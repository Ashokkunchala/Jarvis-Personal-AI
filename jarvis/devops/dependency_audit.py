"""Offline summary of supplied pip-audit JSON. Never installs, scans or fixes."""
from __future__ import annotations

import json
import re
from pathlib import Path

SOURCE = 'https://github.com/pypa/pip-audit'
FORMAT_SOURCE = 'https://raw.githubusercontent.com/pypa/pip-audit/main/pip_audit/_format/json.py'


def _text(value, label, pattern, maximum=200):
    if not isinstance(value, str) or len(value) > maximum or not re.fullmatch(pattern, value):
        raise ValueError(f'Invalid {label}; supply unmodified pip-audit JSON.')
    return value


def _strings(values, label, pattern):
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError(f'{label} must be an array of at most 100 strings.')
    return sorted({_text(value, label, pattern) for value in values})


def review_audit(document):
    if isinstance(document, dict):
        dependencies = document.get('dependencies')
        format_name = 'dependencies-object'
        fixes_present = bool(document.get('fixes'))
    elif isinstance(document, list):
        dependencies = document
        format_name = 'legacy-array'
        fixes_present = False
    else:
        raise ValueError('Expected pip-audit dependencies object or legacy dependency array.')
    if not isinstance(dependencies, list) or len(dependencies) > 1000:
        raise ValueError('Supply at most 1000 dependencies.')
    packages, seen, advisory_ids = [], set(), set()
    affected = skipped = no_findings = total_findings = 0
    for dep in dependencies:
        if not isinstance(dep, dict):
            raise ValueError('Every dependency must be an object.')
        name = _text(dep.get('name'), 'package name', r'[A-Za-z0-9][A-Za-z0-9._-]*')
        canonical = re.sub(r'[-_.]+', '-', name).lower()
        # One resolved version per canonical package, matching pip-audit's environment model.
        if canonical in seen:
            raise ValueError('Duplicate canonical package names are ambiguous; scope the audit first.')
        seen.add(canonical)
        if 'skip_reason' in dep:
            skipped += 1
            packages.append({'name': canonical, 'status': 'skipped',
                             'notice': 'Not audited according to supplied export. Free-form skip reason omitted.'})
            continue
        version = _text(dep.get('version'), 'installed version', r'[A-Za-z0-9][A-Za-z0-9.!+_-]*')
        vulns = dep.get('vulns')
        if not isinstance(vulns, list) or len(vulns) > 100:
            raise ValueError('Every resolved package needs a vulns array with at most 100 entries.')
        findings, package_ids = [], set()
        for vuln in vulns:
            if not isinstance(vuln, dict):
                raise ValueError('Every advisory must be an object.')
            identifier = _text(vuln.get('id'), 'advisory ID', r'[A-Za-z0-9][A-Za-z0-9._:-]*')
            if identifier in package_ids:
                raise ValueError('Duplicate advisory IDs for one package are ambiguous.')
            package_ids.add(identifier)
            advisory_ids.add(identifier)
            fixes = _strings(vuln.get('fix_versions'), 'reported fix versions', r'[A-Za-z0-9][A-Za-z0-9.!+_-]*')
            aliases = _strings(vuln.get('aliases', []), 'advisory aliases', r'[A-Za-z0-9][A-Za-z0-9._:-]*')
            findings.append({'id': identifier, 'aliases': aliases, 'reported_fix_versions': fixes,
                             'fix_status': 'versions_reported' if fixes else 'none_reported_in_export'})
        total_findings += len(findings)
        if total_findings > 2000:
            raise ValueError('Scope the export to at most 2000 package-advisory pairs.')
        if findings:
            affected += 1
        else:
            no_findings += 1
        packages.append({'name': canonical, 'version': version,
                         'status': 'advisories_reported' if findings else 'none_reported_in_export',
                         'findings': findings})
    return {'format': format_name, 'dependencies_reviewed': len(dependencies),
            'packages_with_advisories': affected, 'skipped_packages': skipped,
            'packages_without_reported_advisories': no_findings,
            'package_advisory_pairs': total_findings, 'distinct_reported_primary_ids': len(advisory_ids),
            'packages': packages, 'fix_records_present_but_not_evaluated': fixes_present,
            'source': SOURCE, 'format_source': FORMAT_SOURCE,
            'limits': 'Supplied export only; scan time, inventory completeness, advisory freshness and actual installed versions are not verified. Skipped or absent findings do not mean secure. No severity, exploitability, reachability, compatibility or recommended upgrade is inferred. Aliases are not merged into deduplicated vulnerability counts; pair counts can overlap across advisories. Reported fix versions are not verified safe or sufficient and an empty list does not prove no fix exists. Free-form descriptions, skip reasons and fix execution records are omitted. No scan, network request, package install/update, remediation, alert or account access performed.'}


def review_audit_export(path):
    source = Path(path).expanduser()
    if source.suffix.lower() != '.json' or not source.is_file():
        raise ValueError('Choose an existing local .json pip-audit export, not a path to scan.')
    with source.open('rb') as stream:
        payload = stream.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError('Export exceeds the 2 MB review limit.')
    try:
        document = json.loads(payload.decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Export must be valid UTF-8 JSON.') from exc
    return review_audit(document)


def register_audit_tools(registry):
    from jarvis.tools.registry import Risk, Tool
    registry.register(Tool(name='review_dependency_audit',
                           description='Summarize an existing local pip-audit JSON export, including skipped packages and reported fix versions. Offline evidence review, not a scan, severity score, upgrade recommendation or proof of security. Raw descriptions omitted.',
                           parameters={'type': 'object', 'properties': {'path': {'type': 'string', 'description': 'Existing local pip-audit JSON export, max 2 MB; current object and legacy array supported.'}}, 'required': ['path']},
                           handler=review_audit_export, risk=Risk.SAFE, category='devops'))
