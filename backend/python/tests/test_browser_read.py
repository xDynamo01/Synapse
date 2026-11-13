import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('browser_read', Path(__file__).parents[1] / 'synapse_ai/browser_read.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class BrowserReadTests(unittest.TestCase):
    def test_rejects_foreign_origin_before_dns(self):
        with patch.object(reader, 'resolve') as resolve:
            with self.assertRaisesRegex(ValueError, 'approved origin'):
                reader.fetch('https://example.com', 'https://other.example.com')
            resolve.assert_not_called()

    def test_rejects_mixed_dns_answers(self):
        records = [(None, None, None, None, (ip, 443)) for ip in ('93.184.216.34', '127.0.0.1')]
        with patch.object(reader.socket, 'getaddrinfo', return_value=records):
            with self.assertRaisesRegex(ValueError, 'nonpublic'):
                reader.resolve('example.com')

    def test_parser_extracts_text_without_script_or_style(self):
        parser = reader.PageText()
        parser.feed('<h1>Title</h1><script>secret()</script><style>.a {}</style><p>Body</p>')
        self.assertEqual(parser.parts, ['Title', 'Body'])

    def test_rejects_unsupported_addresses(self):
        for url in ('https://127.1', 'https://example.com:8443', 'https://u@example.com', 'https://host.local', 'file:///x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                reader.target(url)

    def test_parser_lists_image_sources_without_requesting_them(self):
        parser = reader.PageText()
        with patch.object(reader.socket, 'getaddrinfo') as resolve:
            parser.feed('<img src="/photo.png" srcset="/automatic.jpg 2x">'
                        '<script><img src="/hidden.png"></script>'
                        '<img src="broken address"><iframe src="/frame"></iframe>')
            resolve.assert_not_called()
        self.assertEqual(parser.images, ['/photo.png'])

    def test_login_preserves_hidden_fields_and_rejects_ambiguous_password(self):
        parser = reader.PageText()
        parser.feed('<form method="post" action="/login"><input name="u"><input name="p" type="password"><input type="hidden" name="csrf" value="test-token"></form>')
        form, = parser.forms
        login = dict(username_field='u', password_field='p', username='test+user', password='test&password')
        self.assertEqual(reader.encode_login(form, login), b'u=test%2Buser&p=test%26password&csrf=test-token')
        form['fields'].append(('second', 'password', ''))
        with self.assertRaisesRegex(ValueError, 'Unsupported login fields'):
            reader.encode_login(form, login)

    def test_login_rejects_foreign_form_before_sending_credentials(self):
        from email.message import Message
        from unittest.mock import MagicMock
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.getpeername.return_value = ('93.184.216.34', 443)
        tls = MagicMock()
        tls.__enter__.return_value = tls
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = Message()
        response.headers['Content-Type'] = 'text/html'
        response.getheader.side_effect = lambda key, default=None: response.headers.get(key, default)
        response.info.return_value = response.headers
        response.read1.side_effect = [b'<form method="post" action="https://other.example.com/login"><input name="u"><input name="p" type="password"></form>', b'']
        login = dict(action='https://example.com/login', username_field='u', password_field='p', username='fictional', password='fictional-secret')
        with patch.object(reader, 'resolve', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))]), patch.object(reader.socket, 'socket', return_value=connection), patch.object(reader.ssl, 'create_default_context') as context, patch.object(reader, 'HTTPResponse', return_value=response):
            context.return_value.wrap_socket.return_value = tls
            with self.assertRaisesRegex(ValueError, 'confirmed endpoint'):
                reader.fetch('https://example.com', 'https://example.com/login', login=login)
        tls.sendall.assert_called_once()
        self.assertNotIn(b'fictional-secret', tls.sendall.call_args.args[0])

    def test_cross_origin_redirect_reports_only_the_host(self):
        approved = reader.target('https://test.wikipedia.org')
        with self.assertRaises(reader.NavigationDenied) as denied:
            reader.redirect_destination('https://test.wikipedia.org/login',
                                        'https://auth.wikimedia.org/login?token=opaque', approved)
        self.assertIn('auth.wikimedia.org', str(denied.exception))
        self.assertNotIn('opaque', str(denied.exception))
        self.assertEqual(reader.redirect_destination('https://test.wikipedia.org/login', '/done', approved),
                         'https://test.wikipedia.org/done')

    def test_central_return_requires_submission_and_exact_hosts(self):
        auth = reader.target('https://auth.wikimedia.org')
        start = 'https://auth.wikimedia.org/testwiki/wiki/Special:UserLogin'
        wiki = 'https://test.wikipedia.org/wiki/Main_Page'
        self.assertEqual(reader.login_redirect(start, wiki, auth, True, True), wiki)
        for url, submitted in [(wiki, False), ('https://evil.example.com/', True)]:
            with self.assertRaises(reader.NavigationDenied):
                reader.login_redirect(start, url, auth, True, submitted)

    def test_session_proof_requires_the_expected_nonanonymous_account(self):
        def proof(user):
            import json
            return reader.verified_identity(json.dumps({'query': {'userinfo': user}}), 'QA User')
        self.assertTrue(proof({'id': 12, 'name': 'QA_User'}))
        self.assertFalse(proof({'id': 12, 'name': 'Other'}))
        self.assertFalse(proof({'id': 0, 'name': 'QA User', 'anon': True}))

    @unittest.skipUnless(__import__('os').name == 'nt', 'Windows DPAPI')
    def test_encrypted_session_round_trip(self):
        import tempfile
        from http.cookiejar import Cookie, CookieJar
        with tempfile.TemporaryDirectory() as directory, patch.object(reader, 'session_file', return_value=Path(directory) / 'profile'):
            jar = CookieJar()
            jar.set_cookie(Cookie(0, 'session', 'fictional-test-cookie', None, False, 'test.wikipedia.org', False, False, '/', True, True, None, True, None, None, {}))
            reader.save_session('fictional-account', jar)
            self.assertNotIn(b'fictional-test-cookie', reader.session_file().read_bytes())
            username, restored = reader.load_session()
            self.assertEqual(username, 'fictional-account')
            self.assertEqual(next(iter(restored)).value, 'fictional-test-cookie')
