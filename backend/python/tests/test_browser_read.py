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
