# Intelligence operating profiles

- `LOCAL_SOVEREIGN`: only explicitly local boundaries; external providers and
  MCP are blocked.
- `HYBRID_GUARDED`: approved external profiles may process public/internal;
  confidential requires guarded transformation/approval; restricted/secret
  remain local-only.
- `EXTERNAL_ASSISTED`: broader profiled external processing, never without
  classification, manifest and ledger.
- `AIR_GAPPED`: no external network boundary; governed manual import/export
  only.

Profiles are defaults, never bypasses. Asset, project, RFC, mission and Skill
constraints may only restrict them further. Boundary failure closes external
processing while explicitly local processing may continue safely.
