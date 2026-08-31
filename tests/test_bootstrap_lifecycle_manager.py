from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from synapse.bootstrap.lifecycle import (
    LifecycleManager,
    LifecycleResource,
    LifecycleStartupError,
)


class BootstrapLifecycleManagerTests(unittest.TestCase):
    def test_required_startup_failure_reports_resource_and_original_cause(self) -> None:
        manager = LifecycleManager()

        def fail() -> None:
            try:
                raise ValueError("inner config path missing")
            except ValueError as exc:
                raise RuntimeError("outer startup failed") from exc

        manager.register(LifecycleResource("required-db", start=fail, required=True))
        output = io.StringIO()

        with redirect_stdout(output), self.assertRaises(LifecycleStartupError) as raised:
            manager.start()

        error = raised.exception
        self.assertIn("resource=required-db", str(error))
        self.assertIn("cause=RuntimeError: outer startup failed", str(error))
        self.assertIsInstance(error.__cause__, RuntimeError)
        self.assertIsNotNone(error.failed)
        assert error.failed is not None
        self.assertTrue(error.failed.required)
        self.assertEqual(error.failed.resource, "required-db")
        self.assertEqual(error.failed.error_type, "RuntimeError")
        self.assertIn("ValueError: inner config path missing", error.failed.causal_chain)
        self.assertIn("startup failure: resource=required-db required=True", output.getvalue())

    def test_optional_startup_failure_degrades_without_raising(self) -> None:
        manager = LifecycleManager()
        manager.register(LifecycleResource("required-ok", start=lambda: None, required=True))
        manager.register(
            LifecycleResource(
                "optional-git",
                start=lambda: (_ for _ in ()).throw(RuntimeError("not a checkout")),
                required=False,
            )
        )

        report = manager.start()

        self.assertEqual(report.status, "degraded")
        failed = [item for item in report.results if item.status == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].resource, "optional-git")
        self.assertFalse(failed[0].required)


if __name__ == "__main__":
    unittest.main()
