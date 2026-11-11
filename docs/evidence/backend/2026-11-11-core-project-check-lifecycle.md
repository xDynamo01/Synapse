# Durable native checks through the Core CLI

Core schema 10 stores the check ID, the sealed mission and candidate digests,
the staged tool digest, the private run directory, status, cleanup state and
the parent-observed phase receipt. The Core authorizes the launch after staging
the tools and committing their digest. Its writer loop continues processing
native events while stdin is idle.

The preimplementation test reached an approved mission and received
`invalid_request` for `project_check_start`. The configured Windows Python
CLI fixture then passed approval gating, candidate mismatch, idempotent replay,
changed retries, successful contained execution, cancellation of an active
test, graceful EOF, abrupt restart and mission revocation. The workspace
remained empty. Following abrupt exit, the persisted cleanup state remains
`unverified` and the check is not replayed.

The Rust CLI fixture initially emitted objects and failed in the linker with
permission denied. The pinned LLD startup uses `GetLongPathNameW` on its
executable path. Configuring the staging parent at the tested local volume
root allowed the CLI to emit, link and execute successfully under the same
verified LPAC policy. Core creates and protects a fresh child directory and
does not change parent directory permissions. The staging child is created with a protected owner/System DACL before descendant creation. Canonical staging paths inside the Workspace are rejected. [LLVM Windows startup](https://raw.githubusercontent.com/llvm/llvm-project/llvmorg-22.1.2/llvm/lib/Support/Windows/Process.inc)

The all-features regression run passed 59 CLI tests and one native identity
unit test. The schema migration fixture now removes the schema-10 table before
simulating schema 6. The existing direct native Rust fixture was also rerun
and passed.

The native check API is described in [protocol v1](../../../backend/contracts/v1/README.md).
Source generation, separate QA and automatic integration are later mission
coordinator work. Automatic deletion after abrupt exit remains unimplemented.
