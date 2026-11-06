import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { Client } from '../client/main-process-client.js';
import { Server } from './server-harness.js';

const candidates = process.env.TRANSPORT ? [process.env.TRANSPORT] : ['grpc', 'http'];
for (const candidate of candidates) {
  test(`${candidate}: typed main-process client survives killed Core without duplicate admission`, { timeout: 20000 }, async () => {
    await mkdir('.local', { recursive: true });
    const dir = await mkdtemp(join('.local', 'node-test-'));
    const server = new Server(candidate, join(dir, 'journal.sqlite'));
    let client: Client | undefined;
    try {
      await server.start();
      client = new Client(candidate, server.port);
      assert.deepEqual(await client.call('GetStatus'), {
        healthy: true, contract_version: '1.0', last_event_id: '0', command_count: 0,
      });
      const request = { command_id: 'ts-one', causation_id: 'owner', action: 'hold' };
      const first = await client.call('SubmitCommand', request);
      assert.deepEqual(first, { state: 'ACKNOWLEDGED', contract_version: '1.0', event_id: '1',
        command_id: 'ts-one', causation_id: 'owner', duplicate: false });
      const stream = await client.events('0');
      assert.deepEqual(await stream.next(), first);
      await server.kill();
      // The broken connection must surface failure rather than hang or retry a command.
      await assert.rejects(stream.next());
      stream.close();
      client.close();
      await server.start();
      client = new Client(candidate, server.port);
      assert.deepEqual(await client.call('SubmitCommand', request), { ...first, duplicate: true });
      assert.equal((await client.call('GetStatus')).command_count, 1);
      assert.equal((await client.call('CancelCommand', { command_id: 'ts-one', causation_id: 'owner-cancel' })).state, 'CANCELLED');
      const replay = await client.events('1');
      const event = await replay.next();
      assert.equal(event.event_id, '2');
      assert.equal(event.state, 'CANCELLED');
      replay.close();
      assert.equal((await client.call('GetStatus', {}, 'wrong')).error?.code, 'UNAUTHENTICATED');
      assert.equal((await client.call('GetStatus', { contract_version: '2.0' })).error?.code, 'INCOMPATIBLE_VERSION');
      for (const [token, version, code] of [
        ['wrong', '1.0', 'UNAUTHENTICATED'],
        [undefined, '2.0', 'INCOMPATIBLE_VERSION'],
      ] as const) {
        const rejected = await client.events('0', true, token, version);
        assert.equal((await rejected.next()).error?.code, code);
        rejected.close();
      }
      const stalled = await client.events('0', false);
      assert.equal((await stalled.next()).event_id, '1');
      assert.deepEqual((await stalled.next()).error, {
        code: 'BACKPRESSURE', message: 'Event acknowledgement deadline exceeded',
        retryable: true, last_event_id: '0',
      });
      stalled.close();
      client.close();
      await server.stop();
    } finally {
      client?.close();
      await server.kill();
      await rm(dir, { recursive: true, force: true });
    }
  });
}
