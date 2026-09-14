/** Bound React updates, not microphone sampling or voice activity detection. */
export function createPresencePublicationGate(intervalMs = 80): (phase: string, amplitude: number, now: number) => boolean {
  let previousPhase: string | undefined;
  let previousAmplitude = -1;
  let lastPublished = -Infinity;
  return (phase, amplitude, now) => {
    const changedPhase = phase !== previousPhase;
    if (!changedPhase && (now - lastPublished < intervalMs || Math.abs(amplitude - previousAmplitude) < 0.01)) return false;
    previousPhase = phase;
    previousAmplitude = amplitude;
    lastPublished = now;
    return true;
  };
}
