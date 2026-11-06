import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { test } from 'node:test';
import type { RuntimeStatus } from '../generated/status.js';

test('ESM and generated contract types', () => {
  assert.ok(import.meta.url.endsWith('runtime-client.test.js'));
  const status: RuntimeStatus = { contract_version: '1', state: 'ready' };
  assert.equal(status.state, 'ready');
  // These directives fail compilation if generation weakens the contract.
  // @ts-expect-error incompatible version must be rejected by the generated type
  const wrongVersion: RuntimeStatus = { contract_version: '2', state: 'ready' };
  // @ts-expect-error invalid state must be rejected by the generated type
  const wrongState: RuntimeStatus = { contract_version: '1', state: 'unknown' };
  void wrongVersion;
  void wrongState;
});

test('child process cancellation closes pipes and reaps the child', { timeout: 5000 }, async () => {
  const controller = new AbortController();
  const child = spawn(process.execPath, ['--input-type=module', '-e',
    "process.stdout.write('ready'); setInterval(() => {}, 1000);"],
    { signal: controller.signal, timeout: 4000, stdio: ['ignore', 'pipe', 'pipe'] });
  const errors: Error[] = [];
  child.on('error', error => errors.push(error));
  const closed = new Promise<[number | null, NodeJS.Signals | null]>(resolve => {
    child.once('close', (code, signal) => resolve([code, signal]));
  });
  try {
    const [ready] = await once(child.stdout!, 'data');
    assert.equal(ready.toString(), 'ready');
    controller.abort();
    const [code, signal] = await closed;
    assert.ok(signal !== null || code !== 0);
    assert.equal(errors.length, 1);
    assert.equal(errors[0].name, 'AbortError');
    assert.equal(child.stdout!.destroyed, true);
    assert.equal(child.stderr!.destroyed, true);
    assert.throws(() => process.kill(child.pid!, 0), /ESRCH/);
  } finally {
    if (child.exitCode === null && child.signalCode === null) child.kill();
  }
});

test('a normal child exits cleanly with no residual handles', { timeout: 5000 }, async () => {
  const child = spawn(process.execPath, ['--input-type=module', '-e',
    "await Promise.resolve(); process.stdout.write(JSON.stringify({state:'ready'}));"],
    { timeout: 4000, stdio: ['ignore', 'pipe', 'pipe'] });
  let stdout = '';
  let stderr = '';
  child.stdout!.on('data', chunk => { stdout += chunk; });
  child.stderr!.on('data', chunk => { stderr += chunk; });
  const [code, signal] = await once(child, 'close');
  assert.equal(code, 0);
  assert.equal(signal, null);
  assert.deepEqual(JSON.parse(stdout), { state: 'ready' });
  assert.equal(stderr, '');
});
