/** Experiment-only Node client. The future Electron integration imports this boundary in main only. */
import * as grpc from '@grpc/grpc-js';
import { loadSync } from '@grpc/proto-loader';
import WebSocket from 'ws';
import { resolve } from 'node:path';
import type { ProtoGrpcType } from '../generated/ts/lifecycle.js';
import type { LifecycleClient } from '../generated/ts/synapse/foundation/v1/Lifecycle.js';
import type { Envelope } from '../generated/ts/synapse/foundation/v1/Envelope.js';
import type { CommandRequest } from '../generated/ts/synapse/foundation/v1/CommandRequest.js';
import type { StatusRequest } from '../generated/ts/synapse/foundation/v1/StatusRequest.js';
import type { CancelRequest } from '../generated/ts/synapse/foundation/v1/CancelRequest.js';
import type { SubscribeFrame } from '../generated/ts/synapse/foundation/v1/SubscribeFrame.js';

const TEST_TOKEN = 'synapse-transport-spike-test-only';
type Requests = { GetStatus: StatusRequest; SubmitCommand: CommandRequest; CancelCommand: CancelRequest };
type TransportTermination =
  | { transport: 'grpc'; code: grpc.status }
  | { transport: 'websocket'; code: number };
const schema = resolve('proto/synapse/foundation/v1/lifecycle.proto');
const definition = grpc.loadPackageDefinition(loadSync(schema, {
  keepCase: true, longs: String,
})) as unknown as ProtoGrpcType;

export class Client {
  private stub?: LifecycleClient;
  private streams = new Set<EventStream>();
  constructor(private candidate: string, private port: number) {
    const processType = (process as NodeJS.Process & { type?: string }).type;
    if (processType !== undefined && processType !== 'browser') {
      throw new Error('Core transport belongs in Electron main');
    }
    if (!['grpc', 'http'].includes(candidate)) throw new Error('Unknown candidate');
    if (candidate === 'grpc') this.stub = new definition.synapse.foundation.v1.Lifecycle(
      `127.0.0.1:${port}`, grpc.credentials.createInsecure(),
      { 'grpc.enable_http_proxy': 0, 'grpc.enable_retries': 0 });
  }
  private metadata(token: string) {
    const metadata = new grpc.Metadata();
    metadata.set('authorization', `Bearer ${token}`);
    return metadata;
  }
  async call<Method extends keyof Requests>(method: Method, request: Requests[Method] = {}, token = TEST_TOKEN): Promise<Envelope> {
    const body = { contract_version: '1.0', ...request };
    if (this.stub) return new Promise((resolve, reject) => {
      this.stub![method](body, this.metadata(token), { deadline: Date.now() + 3000 }, (error, value) => {
        if (error) reject(error); else if (value) resolve(value); else reject(new Error('Missing response'));
      });
    });
    const response = await fetch(`http://127.0.0.1:${this.port}/v1/${method}`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json() as Envelope;
  }
  async events(after_event_id: string, acknowledge = true, token = TEST_TOKEN, version = '1.0'): Promise<EventStream> {
    const opening = { contract_version: version, after_event_id };
    if (this.stub) {
      const wire = this.stub.SubscribeEvents(this.metadata(token));
      const transportTermination = new Promise<TransportTermination>(resolve => {
        wire.once('status', ({ code }) => resolve({ transport: 'grpc', code }));
      });
      const stream = new EventStream(acknowledge, version, frame => { wire.write(frame); },
        () => { this.streams.delete(stream); wire.cancel(); }, transportTermination);
      this.streams.add(stream);
      wire.on('data', (event: Envelope) => stream.push(event));
      wire.on('error', error => stream.fail(error));
      wire.on('end', () => stream.fail(new Error('Event stream ended')));
      wire.write(opening);
      return stream;
    }
    const wire = new WebSocket(`ws://127.0.0.1:${this.port}/v1/SubscribeEvents`, {
      headers: { Authorization: `Bearer ${token}` }, handshakeTimeout: 3000, maxPayload: 4096,
    });
    const transportTermination = new Promise<TransportTermination>(resolve => {
      wire.once('close', code => resolve({ transport: 'websocket', code }));
    });
    const stream = new EventStream(acknowledge, version, frame => wire.send(JSON.stringify(frame)),
      () => { this.streams.delete(stream); wire.terminate(); }, transportTermination);
    this.streams.add(stream);
    wire.on('message', data => {
      try { stream.push(JSON.parse(data.toString()) as Envelope); }
      catch { stream.fail(new Error('Malformed event')); }
    });
    wire.on('error', error => stream.fail(error));
    wire.on('close', () => stream.fail(new Error('Event stream closed')));
    try {
      await new Promise<void>((resolve, reject) => { wire.once('open', resolve); wire.once('error', reject); });
      wire.send(JSON.stringify(opening));
      return stream;
    } catch (error) {
      stream.close();
      throw error;
    }
  }
  close() {
    for (const stream of this.streams) stream.close();
    this.stub?.close();
  }
}

export class EventStream {
  private queue: Envelope[] = [];
  private error?: Error;
  private closed = false;
  private waiting?: { resolve: (value: Envelope) => void; reject: (error: Error) => void };
  constructor(private acknowledge: boolean, private version: string,
    private send: (frame: SubscribeFrame) => void, private dispose: () => void,
    readonly transportTermination: Promise<TransportTermination>) {}
  push(event: Envelope) {
    if (this.closed) return;
    if (this.waiting) { const waiter = this.waiting; this.waiting = undefined; waiter.resolve(event); }
    else if (this.queue.length < 2) this.queue.push(event);
    else this.close(new Error('Client event bound exceeded'));
  }
  fail(error: Error) {
    this.error ??= error;
    this.waiting?.reject(error);
    this.waiting = undefined;
  }
  async next(): Promise<Envelope> {
    const queued = this.queue.shift();
    if (!queued && this.error) throw this.error;
    if (this.waiting) throw new Error('Only one event reader is permitted');
    const event = queued ?? await new Promise<Envelope>((resolve, reject) => {
      const timer = setTimeout(() => this.close(new Error('Event read deadline exceeded')), 3000);
      this.waiting = {
        resolve: value => { clearTimeout(timer); resolve(value); },
        reject: error => { clearTimeout(timer); reject(error); },
      };
    });
    if (event.event_id && this.acknowledge) this.send({ contract_version: this.version, ack_event_id: event.event_id });
    return event;
  }
  close(error = new Error('Event stream disposed')) {
    if (this.closed) return;
    this.closed = true;
    this.queue = [];
    this.fail(error);
    this.dispose();
  }
}
