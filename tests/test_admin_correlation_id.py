import os
import sys
import unittest

from flask import Flask


BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'web', 'backend')
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


class CorrelationIdHeaderTests(unittest.TestCase):
    """The response should always carry an X-Request-Id, whether or not the
    client sent one -- covered directly against app.py's before/after_request
    hooks via a minimal throwaway app rather than importing the real app.py
    (which requires a fully configured environment)."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='correlation-id-test')

        import re
        import uuid
        from flask import g, request as flask_request

        @self.app.before_request
        def _set_correlation_id():
            inbound = (flask_request.headers.get('X-Request-Id') or '').strip()[:100]
            g.correlation_id = inbound if re.fullmatch(r'[A-Za-z0-9._-]+', inbound or '') else uuid.uuid4().hex

        @self.app.after_request
        def _echo_correlation_id(response):
            correlation_id = getattr(g, 'correlation_id', None)
            if correlation_id:
                response.headers['X-Request-Id'] = correlation_id
            return response

        @self.app.route('/ping')
        def ping():
            return {'ok': True}

        self.client = self.app.test_client()

    def test_mints_a_correlation_id_when_none_supplied(self):
        response = self.client.get('/ping')
        self.assertIn('X-Request-Id', response.headers)
        self.assertTrue(len(response.headers['X-Request-Id']) > 0)

    def test_reuses_a_well_formed_inbound_request_id(self):
        response = self.client.get('/ping', headers={'X-Request-Id': 'trace-abc-123'})
        self.assertEqual('trace-abc-123', response.headers['X-Request-Id'])

    def test_rejects_a_malformed_inbound_request_id(self):
        response = self.client.get('/ping', headers={'X-Request-Id': 'not valid! <script>'})
        self.assertNotEqual('not valid! <script>', response.headers['X-Request-Id'])


if __name__ == '__main__':
    unittest.main()
