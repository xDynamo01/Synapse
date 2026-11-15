import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('browser_read', Path(__file__).parents[1] / 'synapse_ai/browser_read.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class BrowserReadTests(unittest.TestCase):
    def test_skill_catalog_keeps_packages_on_origin(self):
        source = 'https://example.com/skills/index.json'
        with patch.object(reader, 'resolve') as resolve:
            catalog = reader.skill_catalog({
                'source': source,
                'document': json.dumps([{'name': 'Example', 'url': 'example.json'}]),
            })
            self.assertEqual(catalog['packages'], [
                {'name': 'Example', 'url': 'https://example.com/skills/example.json'},
            ])
            with self.assertRaisesRegex(ValueError, 'outside the catalog origin'):
                reader.skill_catalog({
                    'source': source,
                    'document': json.dumps([{'name': 'Other', 'url': '//other.example.com/package'}]),
                })
            resolve.assert_not_called()

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

    def test_public_reader_never_replays_server_cookies(self):
        from email.message import Message
        from unittest.mock import MagicMock

        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.getpeername.return_value = ("93.184.216.34", 443)
        tls = MagicMock()
        tls.__enter__.return_value = tls

        def response(status, headers, chunks):
            reply = MagicMock()
            reply.__enter__.return_value = reply
            reply.status = status
            reply.headers = Message()
            for name, value in headers.items():
                reply.headers[name] = value
            reply.getheader.side_effect = reply.headers.get
            reply.read1.side_effect = chunks
            return reply

        redirect = response(302, {"Location": "/next", "Set-Cookie": "session=fake"}, [])
        page = response(200, {"Content-Type": "text/html"},
                        [b'<img src="/photo.png"><script>ignored</script>Visible', b""])
        addresses = [(2, 1, 6, "", ("93.184.216.34", 443))]
        with patch.object(reader, "resolve", return_value=addresses), \
             patch.object(reader.socket, "socket", return_value=connection), \
             patch.object(reader.ssl, "create_default_context") as context, \
             patch.object(reader, "HTTPResponse", side_effect=[redirect, page]):
            context.return_value.wrap_socket.return_value = tls
            result = reader.fetch("https://example.com", "https://example.com/start",
                                  mission=True)
            self.assertEqual(result, {"redirect": "https://example.com/next"})
            tls.sendall.assert_called_once()
            result = reader.fetch("https://example.com", result["redirect"])

        requests = [call.args[0] for call in tls.sendall.call_args_list]
        self.assertEqual([request.split(b" ", 2)[1] for request in requests], [b"/start", b"/next"])
        self.assertTrue(all(request.startswith(b"GET ") and b"Cookie:" not in request
                            for request in requests))
        self.assertEqual(result["text"], "Visible")
        self.assertEqual(result["images"], ["https://example.com/photo.png"])

    def test_cross_origin_redirect_reports_only_the_host(self):
        approved = reader.target('https://test.wikipedia.org')
        with self.assertRaises(reader.NavigationDenied) as denied:
            reader.redirect_destination('https://test.wikipedia.org/login',
                                        'https://auth.wikimedia.org/login?token=opaque', approved)
        self.assertIn('auth.wikimedia.org', str(denied.exception))
        self.assertNotIn('opaque', str(denied.exception))
        self.assertEqual(reader.redirect_destination('https://test.wikipedia.org/login', '/done', approved),
                         'https://test.wikipedia.org/done')

    @unittest.skipUnless(__import__('os').name == 'nt', 'Windows DPAPI')
    def test_quarantine_encrypts_valid_text_and_rejects_binary(self):
        import tempfile
        import hashlib
        with tempfile.TemporaryDirectory() as directory, patch.object(reader, 'quarantine_directory', return_value=Path(directory) / 'quarantine'):
            with self.assertRaises(ValueError):
                reader.quarantine_text(b'MZ\x00\xff')
            self.assertFalse((Path(directory) / 'quarantine').exists())
            body = b'Disposable fixture\n'
            receipt = reader.quarantine_text(body)
            self.assertEqual(receipt['sha256'], hashlib.sha256(body).hexdigest())
            files = list((Path(directory) / 'quarantine').iterdir())
            self.assertEqual(len(files), 1)
            self.assertNotIn(body, files[0].read_bytes())
            self.assertEqual(reader.protect_session(files[0].read_bytes(), decrypt=True), body)
