import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('.', import.meta.url));
const server = await createServer({ configFile: false, root,
  plugins: [{ name: 'isolated-appearance-components', enforce: 'pre', transform(source, id) {
    if (!id.replaceAll('\\', '/').endsWith('/src/renderer/main.tsx')) return;
    const mount = source.lastIndexOf('createRoot(document.getElementById');
    if (mount < 0) throw new Error('QA mount marker missing');
    return source.slice(0, mount) + '\nexport { SettingsPanel, Composer };';
  }}], server: { host: '127.0.0.1', port: 5186, strictPort: true,
    fs: { allow: [fileURLToPath(new URL('../..', import.meta.url))] } }
});
await server.listen();
server.printUrls();
