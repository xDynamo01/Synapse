import assert from 'node:assert/strict';
import { status as grpcStatus } from '@grpc/grpc-js';
import { test } from 'node:test';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { Client } from '../client/main-process-client.js';
import type { Envelope } from '../generated/ts/synapse/foundation/v1/Envelope.js';
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
      const secondRequest = { ...request, command_id: 'ts-two' };
      const second = await client.call('SubmitCommand', secondRequest);
      assert.equal(second.event_id, '2');
      await server.kill();
      // Event 2 may be buffered by the wire. Observe its failure without consuming the event.
      assert.deepEqual(await stream.transportTermination, candidate === 'grpc'
        ? { transport: 'grpc', code: grpcStatus.UNAVAILABLE }
        : { transport: 'websocket', code: 1006 });
      stream.close();
      client.close();
      await server.start();
      client = new Client(candidate, server.port);
      assert.deepEqual(await client.call('SubmitCommand', request), { ...first, duplicate: true });
      assert.deepEqual(await client.call('SubmitCommand', secondRequest), { ...second, duplicate: true });
      const status = await client.call('GetStatus');
      assert.equal(status.command_count, 2);
      assert.equal(status.last_event_id, '2');
      const replay = await client.events('1');
      assert.deepEqual(await replay.next(), second);
      const cancelled = await client.call('CancelCommand', { command_id: 'ts-one', causation_id: 'owner-cancel' });
      assert.equal(cancelled.event_id, '3');
      assert.equal(cancelled.state, 'CANCELLED');
      assert.deepEqual(await replay.next(), cancelled);
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

  test(`${candidate}: active subscription remains open past ten seconds`, { timeout: 20000 }, async () => {
    await mkdir('.local', { recursive: true });
    const dir = await mkdtemp(join('.local', 'node-test-'));
    const server = new Server(candidate, join(dir, 'journal.sqlite'));
    let client: Client | undefined;
    try {
      await server.start();
      client = new Client(candidate, server.port);
      const stream = await client.events('0');
      const started = performance.now();
      for (let sequence = 1; sequence <= 12; sequence++) {
        if (sequence > 1) await delay(1000);
        const event: Envelope = await client.call('SubmitCommand', {
          command_id: `active-${sequence}`, causation_id: 'owner', action: 'hold',
        });
        assert.equal(event.event_id, String(sequence));
        assert.deepEqual(await stream.next(), event);
      }
      assert.ok(performance.now() - started > 10000);
      client.close();
      await server.stop();
    } finally {
      client?.close();
      await server.kill();
      await rm(dir, { recursive: true, force: true });
    }
  });
}
