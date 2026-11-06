import assert from 'node:assert/strict';

assert.equal(process.versions.node, '24.22.2', 'Use the exact tested Node patch');
assert.match(process.env.npm_config_user_agent ?? '', /^pnpm\/11\.25\.0(?:\s|$)/,
  'Use the exact tested pnpm version');
