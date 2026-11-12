import csv
from pathlib import Path
import runpy
import unittest


VERIFIERS = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / 'core/src/runner/document_checks.py')
)['CHECKS']


class FixedDocumentChecks(unittest.TestCase):
    def test_bounded_deliverables(self):
        cases = [
            ('json', '{"title":"example"}', '{"title":"first","title":"second"}'),
            ('game_level', '{"width":2,"height":1,"tiles":[[0,4]]}',
             '{"width":2,"height":1,"tiles":[[0,true]]}'),
            ('game_level', '{"width":1,"height":1,"tiles":[[65535]]}',
             '{"width":2,"height":1,"tiles":[[1]]}'),
            ('toml', '[metadata]\nversion = "1.0"\n', 'version = {'),
            ('python_manifest', '[project]\nname="demo"\nversion="1.0"\ndependencies=["foo==1.2"]',
             '[project]\nname="demo"\nversion="1.0"\ndependencies=["foo>=1.2"]'),
            ('python_manifest', '[project]\nname="demo"\nversion="1.0"',
             '[project]\nname="demo"\nversion="1.0"\ndependencies=["Foo-Bar==1.2", "foo_bar==1.2"]'),
            ('csv', 'sample,amount\n"A,1",20\n', 'sample,amount\nA\n'),
            ('md', '# Title\n\n```text\ncontent\n```\n', '# Title\n\n```text\ncontent\n'),
            ('svg', '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><rect width="16" height="16"/></svg>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><script>bad</script></svg>'),
            ('svg', '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><text>A &amp; B</text></svg>',
             '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><g><rect></g></rect></svg>'),
            ('vtt', 'WEBVTT\n\n00:01.000 --> 00:02.000\nHello\n',
             'WEBVTT\n\n00:02.000 --> 00:01.000\nHello\n'),
        ]
        for kind, valid, invalid in cases:
            with self.subTest(kind=kind, invalid=invalid):
                VERIFIERS[kind](valid)
                with self.assertRaises((ValueError, csv.Error)):
                    VERIFIERS[kind](invalid)
