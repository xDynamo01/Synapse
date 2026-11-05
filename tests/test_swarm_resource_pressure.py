from types import SimpleNamespace

import pytest

from acceptance.test_insight_system_e2e import SnapshotProvider
from synapse.core.data_dir import DataDir
from synapse.system_insight.models import DiskSnapshot, DiskVolume
from synapse.system_insight.resource_pressure import ResourcePressureRuntime


@pytest.mark.parametrize("used,expected", [(20, True), (99, False)])
def test_swarm_capacity_checks_its_data_disk_not_unrelated_full_volumes(tmp_path, used, expected):
    checked = []
    def inspect_path(path):
        checked.append(path)
        return DiskSnapshot("test", "now", [DiskVolume("data", "ntfs", 100, used, 100-used, used)])
    disk = SimpleNamespace(
        inspect=lambda: DiskSnapshot("test", "now", [DiskVolume("unrelated", "iso", 100, 100, 0, 100)]),
        inspect_path=inspect_path,
    )
    pressure = ResourcePressureRuntime(
        DataDir(tmp_path), SimpleNamespace(inspect=SnapshotProvider().collect_hardware), disk)
    assert not pressure.assess_capacity("other_workload").sufficient
    assert pressure.assess_capacity("ephemeral_swarm").sufficient is expected
    assert pressure.assess_capacity("ephemeral_agent").sufficient is expected
    assert checked == [tmp_path, tmp_path]
