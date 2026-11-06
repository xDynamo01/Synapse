import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { compileFromFile } from 'json-schema-to-typescript';

await mkdir(new URL('../generated/', import.meta.url), { recursive: true });
const declaration = await compileFromFile(fileURLToPath(new URL('../fixtures/status.schema.json', import.meta.url)));
await writeFile(new URL('../generated/status.d.ts', import.meta.url), declaration);
