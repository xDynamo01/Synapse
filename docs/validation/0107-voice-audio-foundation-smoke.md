# 0107 Voice / Audio Foundation Smoke

Goal: confirm the first local voice/audio foundation works end to end without adding TTS, streaming, or wake-word behavior.

## Backend smoke

1. Start the backend with the normal desktop bootstrap.
2. Call:
   - `GET /api/voice/settings`
   - `GET /api/voice/devices`
   - `GET /api/voice/providers`
3. Verify a microphone device can be tested with:
   - `POST /api/voice/devices/{device_id}/test`
4. Create a manual recording:
   - `POST /api/voice/recordings`
5. Confirm the recording can be fetched:
   - `GET /api/voice/recordings/{recording_id}`
6. Attach a manual transcription:
   - `POST /api/voice/recordings/{recording_id}/transcribe`

## Frontend smoke

1. Open the desktop app.
2. Open the Voice panel from the workspace/sidebar.
3. Confirm settings load.
4. Select a microphone and STT provider if available.
5. Capture audio manually.
6. Save the recording.
7. Save a transcription.
8. Confirm the recording appears in the list and the detail panel shows the persisted transcript.

## Expected result

- Voice settings persist locally.
- Microphone devices are visible.
- Manual recordings are saved locally.
- Manual transcription persists.
- No TTS playback, wake word, or streaming is involved.
