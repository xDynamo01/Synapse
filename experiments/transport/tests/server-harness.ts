import assert from 'node:assert/strict';
import { execFile, spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { once } from 'node:events';
import { resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { clearTimeout, setTimeout } from 'node:timers';
import { promisify } from 'node:util';

function bounded<T>(operation: Promise<T>, message: string, ms: number): Promise<T> {
  let timer: NodeJS.Timeout;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([operation, timeout]).finally(() => clearTimeout(timer));
}

export class Server {
  private child?: ChildProcessWithoutNullStreams;
  private closed?: Promise<number | null>;
  private stderr = '';
  port = 0;
  runtimePid = 0;
  constructor(private candidate: string, private journal: string) {}

  async start() {
    assert.equal(this.child, undefined);
    const python = resolve(process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
    const child = spawn(python, ['server/main.py', '--candidate', this.candidate, '--journal', this.journal], {
      windowsHide: true, stdio: 'pipe',
    });
    this.child = child;
    this.stderr = '';
    // Register once at spawn, including a child that fails before its first line.
    const closed = once(child, 'close').then(([code]) => code as number | null);
    this.closed = closed;
    child.stderr.on('data', data => { this.stderr += data.toString(); });
    const lines = createInterface({ input: child.stdout });
    try {
      const first = await bounded(Promise.race([
        once(lines, 'line').then(([line]) => String(line)),
        closed.then(() => { throw new Error(`Server did not start: ${this.stderr.trim()}`); }),
      ]), 'Core readiness deadline exceeded', 10000);
      const ready = JSON.parse(first) as { host: string; candidate: string; port: number; pid: number; parent_pid: number };
      assert.equal(ready.host, '127.0.0.1');
      assert.equal(ready.candidate, this.candidate);
      assert.ok(Number.isInteger(ready.port) && ready.port > 0 && ready.port < 65536);
      assert.ok(Number.isInteger(ready.pid) && ready.pid > 0);
      // On Windows the venv launcher owns the actual interpreter child.
      assert.ok(ready.pid === child.pid || ready.parent_pid === child.pid);
      process.kill(ready.pid, 0);
      this.runtimePid = ready.pid;
      this.port = ready.port;
    } finally {
      lines.close();
    }
  }

  async kill() {
    if (!this.child || !this.closed) return;
    const { child, closed, runtimePid } = this;
    if (child.exitCode === null && child.signalCode === null && child.pid !== undefined) {
      if (runtimePid) {
        try { process.kill(runtimePid, 'SIGKILL'); }
        catch (error) {
          if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error;
        }
      } else {
        // Give an unready owned child its usual shutdown signal first.
        child.stdin.end();
        try { await bounded(closed, 'Unready Core did not exit', 2000); }
        catch (error) {
          if (child.exitCode !== null || child.signalCode !== null) throw error;
          if (process.platform === 'win32') {
            await promisify(execFile)('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'],
              { windowsHide: true, timeout: 3000 });
          } else child.kill('SIGKILL');
        }
      }
    }
    await this.reap(closed, runtimePid);
  }

  async stop() {
    if (!this.child || !this.closed) return;
    this.child.stdin.end();
    const code = await this.reap(this.closed, this.runtimePid);
    assert.equal(code, 0, this.stderr);
    assert.equal(this.stderr, '');
  }

  private async reap(closed: Promise<number | null>, runtimePid: number) {
    const code = await bounded(closed, 'Core close deadline exceeded', 5000);
    if (runtimePid) assert.throws(() => process.kill(runtimePid, 0), { code: 'ESRCH' });
    this.child = undefined;
    this.closed = undefined;
    this.runtimePid = 0;
    return code;
  }
}
