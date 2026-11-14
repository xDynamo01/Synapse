import hashlib
import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from synapse_ai.providers import ProviderError, validate_endpoint, infer, model_instance, _release_model, _cli_model_instance
from synapse_ai.protocol import digest, validate


class ModelLifecycleTests(unittest.TestCase):
    def test_capacity_busy_preserves_existing_model(self):
        models = {"models": [
            {"key": "resident", "loaded_instances": [{"id": "operator"}]},
            {"key": "selected", "loaded_instances": [], "max_context_length": 32768},
        ]}
        with patch.dict(os.environ, {"SYNAPSE_MANAGE_LOCAL_MODELS": "1"}):
            with patch("synapse_ai.providers._json", return_value=models) as api:
                with self.assertRaisesRegex(ProviderError, "model_capacity_busy"):
                    with model_instance("http://127.0.0.1:1234/v1", "selected", 10):
                        self.fail("capacity refusal must occur before inference")
                self.assertEqual(api.call_count, 1)

    def test_reuses_operator_instance_without_unloading_it(self):
        models = {"models": [
            {"key": "selected", "loaded_instances": [{"id": "operator"}], "max_context_length": 32768},
        ]}
        with patch.dict(os.environ, {"SYNAPSE_MANAGE_LOCAL_MODELS": "1"}):
            with patch("synapse_ai.providers._json", return_value=models) as api:
                with model_instance("http://127.0.0.1:1234/v1", "selected", 10) as instance:
                    self.assertEqual(instance, "operator")
                self.assertEqual(api.call_count, 1)

    def test_reconciles_ambiguous_unload(self):
        for instances in ([], [{"id": "owned"}, {"id": "operator"}]):
            with self.subTest(instances=instances):
                catalog = {"models": [{"loaded_instances": instances}]}
                with patch("synapse_ai.providers._json", side_effect=[
                    ProviderError("provider_timeout"), catalog, {},
                ]) as api:
                    _release_model("http://127.0.0.1:1234/api/v1/models", "owned")
                    self.assertEqual(api.call_count, 3 if instances else 2)
                    if instances:
                        self.assertEqual(api.call_args.args[1], {"instance_id": "owned"})

    def test_unload_not_found_is_success_only_if_catalog_confirms_absence(self):
        base = "http://127.0.0.1:1234/api/v1/models"
        for resident in (False, True):
            with self.subTest(resident=resident):
                entries = [{"id": "owned"}] if resident else []
                responses = [
                    ProviderError("model_unavailable"),
                    {"models": [{"loaded_instances": entries}]},
                    ProviderError("model_unavailable"),
                ]
                with patch("synapse_ai.providers._json", side_effect=responses):
                    if resident:
                        with self.assertRaisesRegex(ProviderError, "model_unavailable"):
                            _release_model(base, "owned")
                    else:
                        _release_model(base, "owned")

    def test_cli_mode_does_not_load_against_an_unmatched_endpoint(self):
        catalog = {"models": [
            {"key": "selected", "loaded_instances": [], "max_context_length": 32768},
        ]}
        with patch.dict(os.environ, {
            "SYNAPSE_MANAGE_LOCAL_MODELS": "1",
            "SYNAPSE_LMS_EXECUTABLE": sys.executable,
        }), patch("synapse_ai.providers._json", return_value=catalog) as api:
            with self.assertRaisesRegex(ProviderError, "invalid_endpoint"):
                with model_instance("http://127.0.0.1:4321/v1", "selected", 10):
                    self.fail("an unmatched endpoint must not acquire a model")
            self.assertEqual(api.call_count, 1)

    def test_cli_load_reserves_unique_id_and_sets_expiration(self):
        base = "http://127.0.0.1:1234/api/v1/models"
        with patch("synapse_ai.providers.subprocess.run") as run:
            with patch("synapse_ai.providers._json") as api:
                def catalog(*args, **kwargs):
                    argv = run.call_args.args[0]
                    instance = argv[argv.index("--identifier") + 1]
                    return {"models": [{"key": "selected", "loaded_instances": [{"id": instance}]}]}

                api.side_effect = catalog
                with _cli_model_instance(sys.executable, base, "selected", 32768, 10) as instance:
                    argv = run.call_args.args[0]
                    self.assertTrue(instance.startswith("synapse-"))
                    self.assertEqual(argv[argv.index("--ttl") + 1], "180")
                self.assertEqual(api.call_args.args[:2],
                                 (base + "/unload", {"instance_id": instance}))

    def test_releases_owned_instance_after_failure(self):
        models = {"models": [
            {"key": "selected", "loaded_instances": [], "max_context_length": 65536},
        ]}
        with patch.dict(os.environ, {"SYNAPSE_MANAGE_LOCAL_MODELS": "1"}):
            with patch("synapse_ai.providers._json", side_effect=[models, {"instance_id": "owned"}, {}]) as api:
                with self.assertRaisesRegex(RuntimeError, "inference failed"):
                    with model_instance("http://127.0.0.1:1234/v1", "selected", 10) as instance:
                        self.assertEqual(instance, "owned")
                        raise RuntimeError("inference failed")
                self.assertEqual(api.call_args_list[1].args[1]["context_length"], 32768)
                self.assertEqual(api.call_args.args[1], {"instance_id": "owned"})


class Handler(BaseHTTPRequestHandler):
    mode = "ok"
    def log_message(self, *args):
        pass
    def do_GET(self):
        body = {"data": [{"id": "selected"}]} if self.mode != "missing" else {"data": []}
        self.reply(body)
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        self.server.seen = request
        if self.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.org/")
            self.end_headers()
        elif self.mode == "bad":
            self.reply({"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "x"}], "content": "unsafe"}}]})
        else:
            content = getattr(self.server, "content", "answer")
            self.reply({"choices": [{"message": {"role": "assistant", "content": content}}]})
    def reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class WorkerTests(unittest.TestCase):
    def test_generation_mapping_and_validation(self):
        request = self.request()
        request['version'] = 4
        request['generation'] = {'max_output_tokens': 32, 'timeout_ms': 2000, 'reasoning_effort': 'none'}
        request['digest'] = hashlib.sha256(json.dumps({k:v for k,v in request.items() if k != 'digest'}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        self.assertTrue(self.worker(request)[1]['ok'])
        self.assertEqual(self.server.seen['max_tokens'], 32)
        self.assertEqual(self.server.seen['reasoning_effort'], 'none')
        for effort in ('provider_default', 'low', 'medium', 'high'):
            candidate = request | {'generation': request['generation'] | {'reasoning_effort': effort}}
            candidate['digest'] = hashlib.sha256(json.dumps({k:v for k,v in candidate.items() if k != 'digest'}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
            self.assertTrue(self.worker(candidate)[1]['ok'])
            if effort == 'provider_default':
                self.assertNotIn('reasoning_effort', self.server.seen)
            else:
                self.assertEqual(self.server.seen['reasoning_effort'], effort)
        for key, value in [('max_output_tokens', True), ('max_output_tokens', 0), ('timeout_ms', False), ('timeout_ms', 120001), ('reasoning_effort', 'invalid'), ('extra', 1)]:
            candidate = request | {'generation': request['generation'] | {key: value}}
            with self.assertRaises(ValueError): validate(candidate)
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.seen = None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
    def request(self):
        bare = {"version": 4, "request_id": "r", "model_id": "selected", "endpoint": self.endpoint, "messages": [{"role":"user","content":"private question"}], "generation": {"max_output_tokens":1024,"timeout_ms":10000,"reasoning_effort":"provider_default"}, "purpose":"conversation"}
        digest = hashlib.sha256(json.dumps(bare, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        return bare | {"digest": digest}
    def worker(self, request):
        child = subprocess.run([sys.executable, "-m", "synapse_ai"], input=json.dumps(request).encode()+b"\n", cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        return [json.loads(line) for line in child.stdout.splitlines()]
    def test_handshake_real_loopback_and_bound_request(self):
        hello, answer = self.worker(self.request())
        self.assertEqual(hello, {"type": "hello", "version": 4})
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["content"], "answer")
        self.assertEqual(self.server.seen, {"model": "selected", "messages": [{"role": "user", "content": "private question"}], "stream": False, "max_tokens": 1024})
    def test_digest_and_version_rejected_before_provider(self):
        request = self.request(); request["digest"] = "0" * 64
        self.assertEqual(self.worker(request)[1]["error"], "digest_mismatch")
        request = self.request(); request["version"] = 1
        self.assertEqual(self.worker(request)[1]["error"], "unsupported_version")
        self.assertIsNone(self.server.seen)
    def test_learning_purpose_maps_only_to_static_structured_schema(self):
        request = self.request()
        request['purpose'] = 'learning'
        request['digest'] = hashlib.sha256(json.dumps({k:v for k,v in request.items() if k != 'digest'}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        self.assertTrue(self.worker(request)[1]['ok'])
        schema = self.server.seen['response_format']['json_schema']['schema']
        self.assertEqual(schema['additionalProperties'], False)
        self.assertEqual(schema['properties']['candidates']['maxItems'], 8)
        self.assertNotIn('$ref', json.dumps(schema))
        request['purpose'] = 'other'
        with self.assertRaises(ValueError): validate(request)
        request['version'] = 2
        with self.assertRaises(ValueError): validate(request)
    def test_mission_plan_has_static_strict_bounded_schema_and_version_four(self):
        import re
        from synapse_ai.protocol import digest
        request = self.request() | {'purpose': 'mission_plan'}
        request['digest'] = digest(request)
        hello, answer = self.worker(request)
        self.assertEqual(hello['version'], 4)
        self.assertTrue(answer['ok'])
        schema = self.server.seen['response_format']['json_schema']
        self.assertEqual(schema['name'], 'mission_plan')
        self.assertTrue(schema['strict'])
        body = schema['schema']
        self.assertFalse(body['additionalProperties'])
        self.assertEqual(set(body['required']), {'summary', 'artifacts', 'checks'})
        artifacts = body['properties']['artifacts']
        self.assertEqual((artifacts['minItems'], artifacts['maxItems']), (1, 16))
        self.assertFalse(artifacts['items']['additionalProperties'])
        pattern = artifacts['items']['properties']['path']['pattern']
        for good in ['file.py', 'hello-world.rs', "user's test.txt", 'config.toml', 'level.json', 'survey.csv', 'icon.svg', 'captions.vtt']:
            self.assertIsNotNone(re.fullmatch(pattern, good), good)
        for bad in ['CON.py', 'com1.foo.py', '../x.py', r'dir\\x.py', 'file.exe', 'x.py ', 'x.py.', 'café.py', '😀.py', 'CON .py', 'x?.py', '.py']:
            self.assertIsNone(re.fullmatch(pattern, bad), bad)
        checks = body['properties']['checks']
        self.assertEqual((checks['minItems'], checks['maxItems']), (1, 8))
        expected = {'python_unittest': 'py', 'rust_test': 'rs', 'python_compile': 'py',
                    'json_validate': 'json', 'game_level_validate': 'json', 'toml_validate': 'toml', 'python_manifest_validate': 'toml', 'csv_validate': 'csv',
                    'svg_validate': 'svg', 'markdown_validate': 'md', 'webvtt_validate': 'vtt'}
        recipes = checks['items']['anyOf']
        self.assertEqual({recipe['properties']['kind']['enum'][0] for recipe in recipes}, set(expected))
        for recipe in recipes:
            self.assertFalse(recipe['additionalProperties'])
            fields = recipe['properties']
            kind = fields['kind']['enum'][0]
            suffix = expected[kind]
            self.assertIsNotNone(re.fullmatch(fields['entrypoint']['pattern'], 'test.' + suffix))
            self.assertIsNone(re.fullmatch(fields['entrypoint']['pattern'], 'bad.' + ('rs' if suffix == 'py' else 'py')))
        self.assertNotIn('response_format', request)
        request['version'] = 3
        with self.assertRaises(ValueError): validate(request)

    def test_mission_generation_and_review_use_distinct_static_schemas(self):
        expected = {
            'mission_generate': {'artifacts'},
            'mission_review': {'approved', 'reason'},
        }
        for purpose, required in expected.items():
            with self.subTest(purpose=purpose):
                request = self.request() | {'purpose': purpose}
                if purpose == 'mission_generate':
                    request['messages'] = [{"role": "user", "content": json.dumps(
                        {"artifacts": [{"path": "a.rs"}, {"path": "b.py"}]})}]
                request['digest'] = digest(request)
                hello, answer = self.worker(request)
                self.assertEqual(hello, {"type": "hello", "version": 4})
                self.assertTrue(answer['ok'])
                schema = self.server.seen['response_format']['json_schema']
                self.assertEqual(schema['name'], purpose)
                self.assertIs(schema['strict'], True)
                body = schema['schema']
                self.assertIs(body['additionalProperties'], False)
                self.assertEqual(set(body['required']), required)
                self.assertEqual(set(body['properties']), required)
                if purpose == 'mission_generate':
                    artifacts = body['properties']['artifacts']
                    self.assertEqual((artifacts['minItems'], artifacts['maxItems']), (2, 2))
                    self.assertEqual(artifacts['items']['properties']['path']['enum'], ['a.rs', 'b.py'])
                    item = artifacts['items']
                    self.assertIs(item['additionalProperties'], False)
                    self.assertEqual(set(item['required']), {'path', 'content'})
                    self.assertEqual(item['properties']['content']['maxLength'], 8192)
                else:
                    self.assertEqual(body['properties']['approved']['type'], 'boolean')
                    self.assertEqual(body['properties']['reason']['maxLength'], 2048)
                custom_schema = request | {'response_format': {'type': 'text'}}
                self.assertEqual(self.worker(custom_schema)[1]['error'], 'invalid_request')

    def test_candidate_wire_limits_account_for_json_escaping(self):
        files = [{"path": f"file{index}.txt", "content": "\x01" * 8192} for index in range(3)]
        self.server.content = json.dumps({"artifacts": files})
        self.assertGreater(len(self.server.content), 131072)
        generate = self.request() | {
            "purpose": "mission_generate",
            "messages": [{"role": "user", "content": json.dumps(
                {"artifacts": [{"path": file["path"]} for file in files]})}],
        }
        generate["digest"] = digest(generate)
        self.assertEqual(self.worker(generate)[1]["content"], self.server.content)

        self.server.content = '{"approved":true,"reason":"reviewed"}'
        messages = [{"role": "user", "content": "".join(file["content"] for file in files)}]
        review = self.request() | {"purpose": "mission_review", "messages": messages}
        review["digest"] = digest(review)
        self.assertTrue(self.worker(review)[1]["ok"])
        review["purpose"] = "conversation"
        review["digest"] = digest(review)
        self.assertEqual(self.worker(review)[1]["error"], "invalid_request")

    def test_endpoint_and_model_and_malformed_are_distinct(self):
        for url in ("https://127.0.0.1:1", "http://localhost:1", "http://127.0.0.1:1/v1/other", "http://user@127.0.0.1:1"):
            with self.assertRaises(ProviderError): validate_endpoint(url)
        Handler.mode = "missing"
        self.assertEqual(self.worker(self.request())[1]["error"], "model_unavailable")
        Handler.mode = "bad"
        self.assertEqual(self.worker(self.request())[1]["error"], "provider_malformed")
        Handler.mode = "redirect"
        self.assertEqual(self.worker(self.request())[1]["error"], "provider_redirect")
        Handler.mode = "ok"
    def test_message_schema_and_limits_reject_unsafe_or_incomplete_history(self):
        request=self.request()
        for messages in ([], [{"role":"tool","content":"override"}], [{"role":"assistant","content":"answer"}], [{"role":"user","content":"ok","tool_calls":[]}], [{"role":"user","content":" "}], [{"role":"user","content":"a"*32769}], [{"role":"user","content":"é"*16000}]*2, [{"role":"user","content":"x"}]*65):
            candidate=request | {"messages":messages}
            candidate["digest"]=hashlib.sha256(json.dumps({k:v for k,v in candidate.items() if k != "digest"},sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
            with self.assertRaises(ValueError): validate(candidate)

    def test_invalid_utf8_is_rejected_before_provider(self):
        child = subprocess.run([sys.executable, "-m", "synapse_ai"], input=b'\xff\n', cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout.splitlines()[1])["error"], "invalid_request")
        self.assertIsNone(self.server.seen)

if __name__ == "__main__":
    unittest.main()
