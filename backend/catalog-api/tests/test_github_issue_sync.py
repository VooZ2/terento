from contextlib import contextmanager
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from terento_catalog.github_issue_sync import apply_closed_issue, fetch_issue, sync_once, MAX_ISSUES


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class Connection:
    def __init__(self, rows=(), targets=(), acquired=True):
        self.rows = [dict(row) for row in rows]
        self.targets = list(targets)
        self.acquired = acquired
        self.calls = []

    def execute(self, sql, args=None):
        self.calls.append((sql, args))
        if 'pg_try_advisory' in sql:
            return Result([{'acquired': self.acquired}])
        if 'SELECT DISTINCT substring' in sql:
            return Result(self.targets[:args[0]])
        if 'SELECT event_id' in sql:
            return Result(self.rows)
        if 'UPDATE compatibility_evidence_event' in sql:
            next(row for row in self.rows if row['event_id'] == args[-1])['diagnostic_status'] = 'RESOLVED'
        return Result([])


class Database:
    def __init__(self, connection):
        self.value = connection

    @contextmanager
    def connection(self):
        yield self.value


def event(number, operation='install', issue='#94', status='ACTIVE'):
    return {'event_id': number, 'operation_key': operation,
            'linked_github_issue': issue, 'diagnostic_status': status}


class GitHubIssueSyncTests(unittest.TestCase):
    def test_multi_map_closure_is_audited_once_without_changing_outcomes(self):
        connection = Connection([event(1), event(2), event(3, status='RESOLVED')])
        self.assertEqual(apply_closed_issue(connection, 94, 'completed'), 2)
        self.assertEqual(apply_closed_issue(connection, 94, 'completed'), 0)
        writes = [(sql, args) for sql, args in connection.calls if sql.strip().startswith('UPDATE')]
        self.assertEqual(len(writes), 2)
        for sql, args in writes:
            self.assertNotIn('phase_outcome', sql)
            self.assertNotIn('write_started', sql)
            self.assertEqual(args[:2], ('FIXED', 'FIXED'))
        audits = [args for sql, args in connection.calls if 'INSERT INTO compatibility_diagnostic' in sql]
        self.assertEqual(len(audits), 2)
        self.assertTrue(all(args[-1] == '#94' for args in audits))

    def test_relinked_or_mixed_operation_is_not_resolved(self):
        for issue in ('#95', None):
            connection = Connection([event(1), event(2, issue=issue)])
            self.assertEqual(apply_closed_issue(connection, 94, 'completed'), 0)
            self.assertFalse(any(sql.strip().startswith('UPDATE') for sql, _ in connection.calls))

    def test_not_planned_does_not_claim_fixed(self):
        connection = Connection([event(1)])
        apply_closed_issue(connection, 94, 'not_planned')
        args = next(args for sql, args in connection.calls if sql.strip().startswith('UPDATE'))
        self.assertEqual(args[:2], ('OTHER', 'OTHER'))
        self.assertIn('not_planned', args[2])

    def test_open_issue_keeps_diagnostic_open_and_checks_are_bounded(self):
        connection = Connection([event(1)], [{'issue_number': i} for i in range(1, 21)])
        calls = []
        def fetch(number):
            calls.append(number)
            return {'state': 'open'}
        self.assertEqual(sync_once(Database(connection), fetch=fetch), 0)
        self.assertEqual(len(calls), MAX_ISSUES)
        self.assertEqual(connection.rows[0]['diagnostic_status'], 'ACTIVE')

    def test_rate_limit_stops_batch_and_retains_open_state(self):
        connection = Connection([event(1)], [{'issue_number': 94}, {'issue_number': 95}])
        def fetch(number):
            raise HTTPError('https://api.github.com/', 429, 'limited', {}, None)
        self.assertEqual(sync_once(Database(connection), fetch=fetch), 0)
        self.assertEqual(connection.rows[0]['diagnostic_status'], 'ACTIVE')
        records = [args for sql, args in connection.calls if 'INSERT INTO admin_github_issue_sync' in sql]
        self.assertEqual(records, [(94, None, 'GitHub HTTP 429')])

    def test_fetch_failure_is_visible_without_resolving(self):
        connection = Connection([event(1)], [{'issue_number': 94}])
        def fetch(number):
            raise ValueError('malformed')
        sync_once(Database(connection), fetch=fetch)
        self.assertEqual(connection.rows[0]['diagnostic_status'], 'ACTIVE')
        self.assertTrue(any(args and 'GitHub state could not be verified' in args for _, args in connection.calls))

    def test_second_worker_does_not_poll(self):
        connection = Connection(acquired=False)
        with patch('terento_catalog.github_issue_sync.fetch_issue') as fetch:
            self.assertEqual(sync_once(Database(connection), fetch=fetch), 0)
            fetch.assert_not_called()

    def test_http_boundary_rejects_other_repository_pr_invalid_state_and_oversize(self):
        good = {'number': 94, 'state': 'closed', 'state_reason': 'completed',
                'html_url': 'https://github.com/VooZ2/terento/issues/94'}
        documents = [dict(good, number=95), dict(good, state='unknown'),
                     dict(good, html_url='https://example.com/issues/94'), dict(good, pull_request={})]
        for document in documents:
            with patch('terento_catalog.github_issue_sync.build_opener') as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(document).encode()
                with self.assertRaises(ValueError): fetch_issue(94)
        with patch('terento_catalog.github_issue_sync.build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'x' * 262145
            with self.assertRaises(ValueError): fetch_issue(94)
            response.read.assert_called_once_with(262145)

    def test_valid_http_response_retains_only_state(self):
        with patch('terento_catalog.github_issue_sync.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps({
                'number':94,'state':'closed','state_reason':'completed',
                'html_url':'https://github.com/VooZ2/terento/issues/94', 'body':'not retained',
            }).encode()
            self.assertEqual(fetch_issue(94), {'state':'closed','state_reason':'completed'})
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_method(), 'GET')
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 10)


if __name__ == '__main__':
    unittest.main()
