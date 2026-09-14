// Run with Electron after building the renderer. Exercises the shipped CSP.
const { app, BrowserWindow } = require('electron');
const path = require('node:path');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.whenReady().then(async () => {
  const window = new BrowserWindow({ show: false, webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false } });
  try {
    await window.loadFile(path.join(__dirname, '../dist/renderer/index.html'));
    let sample = null;
    if (process.env.SYNAPSE_AUDIO_TEST_FILE) {
      const fs = require('node:fs/promises');
      sample = {audio_base64: (await fs.readFile(process.env.SYNAPSE_AUDIO_TEST_FILE)).toString('base64')};
    }
    if (process.env.SYNAPSE_AUDIO_TEST_URL) {
      const base = process.env.SYNAPSE_AUDIO_TEST_URL;
      const voices = await (await fetch(base + '/api/voice/voices')).json();
      const voice = voices.find((entry) => entry.usable);
      if (!voice) throw new Error('No usable voice');
      const response = await fetch(base + '/api/audio/synthesize', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Eu sou Artemis.', voice_id: voice.voice_id, provider_id: voice.provider, language: 'pt-BR' })
      });
      if (!response.ok) throw new Error('Synthesis HTTP ' + response.status);
      sample = await response.json();
      if (!sample.audio_base64) throw new Error('No synthesized audio');
    }
    const result = await window.webContents.executeJavaScript(`(async () => {
      const samples = 2400;
      const buffer = new ArrayBuffer(44 + samples * 2);
      const view = new DataView(buffer);
      const label = (offset, text) => [...text].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
      label(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); label(8, 'WAVE');
      label(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
      view.setUint16(22, 1, true); view.setUint32(24, 24000, true); view.setUint32(28, 48000, true);
      view.setUint16(32, 2, true); view.setUint16(34, 16, true); label(36, 'data'); view.setUint32(40, samples * 2, true);
      const sample = ${JSON.stringify(sample)};
      const payload = sample ? Uint8Array.from(atob(sample.audio_base64), c => c.charCodeAt(0)) : buffer;
      const url = URL.createObjectURL(new Blob([payload], { type: 'audio/wav' }));
      const audio = new Audio(url);
      try {
        return await new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error('Playback did not finish')), 10000);
          audio.onended = () => { clearTimeout(timer); resolve({ ended: true, duration: audio.duration }); };
          audio.onerror = () => { clearTimeout(timer); reject(new Error('Media error ' + audio.error?.code)); };
          audio.play().catch(reject);
        });
      } finally { audio.onended = null; audio.onerror = null; audio.pause(); audio.removeAttribute('src'); audio.load(); URL.revokeObjectURL(url); }
    })()`);
    if (!result.ended || !(result.duration > 0)) throw new Error('No playback evidence');
    console.log('PASS: shipped renderer played local WAV through ended', JSON.stringify(result));
    app.exit(0);
  } catch (error) {
    console.error(error);
    app.exit(1);
  }
});
