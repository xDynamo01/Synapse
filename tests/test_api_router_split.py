from __future__ import annotations

import unittest

import synapse.api.routers.system as system_routes
import synapse.api.routes as routes_module
from synapse.api.router_registry import DOMAIN_ROUTERS


class ApiRouterSplitTests(unittest.TestCase):
    def test_system_router_has_system_endpoints(self) -> None:
        paths = {route.path for route in system_routes.router.routes}
        self.assertIn("/health", paths)
        self.assertIn("/system/insight", paths)
        self.assertIn("/readiness", paths)

    def test_registry_flattens_system_router_into_compatibility_router(self) -> None:
        self.assertIn(system_routes.router, DOMAIN_ROUTERS)
        paths = {route.path for route in routes_module.router.routes}
        self.assertIn("/health", paths)
        self.assertIn("/system/insight", paths)
        self.assertIn("/readiness", paths)


if __name__ == "__main__":
    unittest.main()
