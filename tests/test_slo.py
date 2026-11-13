import asyncio

import pytest

from jarvis.devops.slo import review_slo
from jarvis.tools.builtin_tools import build_registry


def window(total=1000, good=999, start='2020-01-01T00:00:00Z', end='2020-01-02T00:00:00Z'):
    return dict(total_events=total, good_events=good, start=start, end=end)


def review(rows=None, target='99.9', complete=True):
    return review_slo([window()] if rows is None else rows, target, complete, 'Good = successful mock requests; all mock requests eligible')


def test_exact_boundary_and_over_budget():
    result = review()
    assert result['objective_met'] and result['remaining_bad_events'] == '0.0'
    assert result['budget_consumed_percent'] == '100' and not result['budget_exceeded']
    result = review([window(good=998)])
    assert not result['objective_met'] and result['budget_exceeded']
    assert result['budget_consumed_percent'] == '200'


def test_weighted_counts_not_average_percentages():
    rows = [window(1, 0), window(999, 999, '2020-01-02T00:00:00Z', '2020-01-03T00:00:00Z')]
    result = review(rows)
    assert result['sli_percent'] == '99.9' and result['objective_met']
    assert review(list(reversed(rows))) == result


def test_zero_events_is_unknown():
    result = review([window(0, 0)])
    assert result['status'] == 'no_data' and result['objective_met'] is None
    assert result['sli_percent'] is None and result['budget_consumed_percent'] is None


def test_hundred_percent_and_fractional_budget():
    result = review([window(10, 10)], '100')
    assert result['zero_error_budget'] and result['objective_met']
    assert result['budget_consumed_percent'] is None
    assert review([window(10, 9)], '100')['budget_exceeded']
    result = review([window(1, 0)], '99.9')
    assert result['allowed_bad_events'] == '0.001' and not result['objective_met']


def test_timezone_offsets_use_real_instants():
    a = window(start='2020-01-01T05:30:00+05:30', end='2020-01-02T05:30:00+05:30')
    b = window(start='2020-01-02T00:00:00Z', end='2020-01-03T00:00:00Z')
    assert review([a, b])['windows_reviewed'] == 2


@pytest.mark.parametrize('target', [0, -1, '100.1', 'NaN', 'Infinity', True, 'bad', '99.1234567890123', 'x' * 50])
def test_invalid_target_rejected(target):
    with pytest.raises(ValueError):
        review(target=target)


@pytest.mark.parametrize('total,good', [(True, 0), (1, True), (1.0, 1), (-1, 0), (1, 2), (1, -1), (10**18+1, 0)])
def test_invalid_counts_rejected(total, good):
    with pytest.raises(ValueError):
        review([window(total, good)])


@pytest.mark.parametrize('start,end', [('2020-01-01', '2020-01-02'), ('bad', '2020-01-02T00:00:00Z'),
                                     ('2020-01-02T00:00:00Z', '2020-01-01T00:00:00Z'),
                                     ('2020-01-01T00:00:00Z', '9999-01-01T00:00:00Z')])
def test_bad_or_unfinished_dates_rejected(start, end):
    with pytest.raises(ValueError):
        review([window(start=start, end=end)])


@pytest.mark.parametrize('start', ['2020-01-01T00:00:00Z', '2020-01-01T12:00:00Z', '2020-01-03T00:00:00Z'])
def test_duplicates_overlaps_and_gaps_rejected(start):
    with pytest.raises(ValueError):
        review([window(), window(start=start, end='2020-01-04T00:00:00Z')])


def test_scope_and_completeness_required():
    for complete in [False, 'true', 1]:
        with pytest.raises(ValueError):
            review(complete=complete)
    for rows in [[], [window()] * 1001, [None]]:
        with pytest.raises(ValueError):
            review(rows)
    with pytest.raises(ValueError):
        review_slo([window()], '99.9', True, ' ')


def test_registry_runs_offline_and_stop_does_not_block_safe_review(tmp_path, monkeypatch):
    from jarvis.security import SecurityStore
    monkeypatch.setenv('JARVIS_SECURITY_DB', str(tmp_path / 'safety.db'))
    SecurityStore().set_stop(True)
    result = asyncio.run(build_registry(force=True).execute('review_slo_budget', dict(windows=[window()], target_percent='99.9', complete_window=True, event_definition='successful mock requests / all mock requests')))
    assert result.ok and result.data['objective_met']
