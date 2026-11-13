import asyncio
import json

import pytest

from jarvis.devops.dependency_audit import review_audit, review_audit_export
from jarvis.tools.builtin_tools import build_registry


def dep(name='example', vulns=None):
    return {'name': name, 'version': '1.0', 'vulns': [] if vulns is None else vulns}


def vuln(identifier='CVE-2020-0001', fixes=None, aliases=None):
    return {'id': identifier, 'fix_versions': ['1.2'] if fixes is None else fixes, 'aliases': [] if aliases is None else aliases}


def test_current_object_legacy_array_and_coverage_counts():
    rows = [dep(vulns=[vuln(aliases=['PYSEC-2020-1'])]), dep('clean-in-export'), {'name': 'private-package', 'skip_reason': 'PRIVATE REASON'}]
    current = review_audit({'dependencies': rows, 'fixes': []})
    legacy = review_audit(rows)
    assert current['dependencies_reviewed'] == 3 and current['packages_with_advisories'] == 1
    assert current['skipped_packages'] == 1 and current['packages_without_reported_advisories'] == 1
    assert current['packages'] == legacy['packages']
    assert 'PRIVATE REASON' not in json.dumps(current)
    assert current['packages'][0]['findings'][0]['reported_fix_versions'] == ['1.2']


def test_no_fabricated_severity_or_upgrade_and_no_fix_claim():
    result = review_audit([dep(vulns=[vuln(fixes=[])])])
    finding = result['packages'][0]['findings'][0]
    assert finding['fix_status'] == 'none_reported_in_export'
    assert 'severity' not in finding and 'recommended_version' not in finding
    assert 'does not prove no fix exists' in result['limits']
    assert review_audit([])['dependencies_reviewed'] == 0
    assert 'do not mean secure' in result['limits']


def test_aliases_not_falsely_deduplicated_and_ids_counted_explicitly():
    a = dep('a', [vuln(aliases=['GHSA-example'])])
    b = dep('b', [vuln(), vuln('PYSEC-2020-1', aliases=['CVE-2020-0001'])])
    result = review_audit([a, b])
    assert result['package_advisory_pairs'] == 3 and result['distinct_reported_primary_ids'] == 2


def test_descriptions_and_fix_execution_records_omitted():
    v = {**vuln(), 'description': 'PRIVATE DESCRIPTION'}
    result = review_audit({'dependencies': [dep(vulns=[v])], 'fixes': [{'new_version': 'PRIVATE FIX RECORD'}]})
    assert result['fix_records_present_but_not_evaluated']
    assert 'PRIVATE' not in json.dumps(result)


@pytest.mark.parametrize('document', [{}, 'text', [None], [dep(), dep('EXAMPLE')], [dep('a_b'), dep('a-b')],
                                     [dep(vulns=[vuln(), vuln()])], [dep(vulns=None)] * 1001,
                                     [dict(name='a', version='1', vulns=None)], [dict(name='a', vulns=[])],
                                     [dep(vulns=[{'id': 'x', 'fix_versions': None}])],
                                     [dep(vulns=[vuln(aliases=['bad\nID'])])], [dep(name='bad; shell')]])
def test_malformed_and_ambiguous_input_rejected(document):
    with pytest.raises(ValueError):
        review_audit(document)


def test_export_file_limits_and_no_raw_error_echo(tmp_path):
    path = tmp_path / 'audit.json'
    for payload in [b'PRIVATE malformed {', b'\xff']:
        path.write_bytes(payload)
        with pytest.raises(ValueError) as exc:
            review_audit_export(str(path))
        assert 'PRIVATE' not in str(exc.value)
    path.write_bytes(b' ' * 2_000_001)
    with pytest.raises(ValueError, match='2 MB'):
        review_audit_export(str(path))


def test_registry_uses_supplied_snapshot_only(tmp_path, monkeypatch):
    from jarvis.security import SecurityStore
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'safety.db'))
    export = tmp_path / 'audit.json'
    export.write_text(json.dumps({'dependencies': [dep(vulns=[vuln()])]}))
    SecurityStore().set_stop(True)
    result = asyncio.run(build_registry(force=True).execute('review_dependency_audit', {'path': str(export)}))
    assert result.ok and result.data['packages_with_advisories'] == 1
    assert result.data['packages'][0]['name'] == 'example'
