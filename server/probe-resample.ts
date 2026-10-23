/** Diagnostic only: independent 20ms frames, no filtering/gain/provider calls. */
export function resampleProbeFrame(pcm: Buffer): Buffer {
  if (pcm.length !== 640) throw new Error('Expected one 16kHz probe frame');
  const output = Buffer.alloc(960);
  for (let i = 0, j = 0; i < 320; i += 2, j += 3) {
    const a = pcm.readInt16LE(i * 2), b = pcm.readInt16LE((i + 1) * 2);
    const c = pcm.readInt16LE(Math.min(i + 2, 319) * 2);
    output.writeInt16LE(a, j * 2);
    output.writeInt16LE(Math.trunc((a + 2 * b) / 3), (j + 1) * 2);
    output.writeInt16LE(Math.trunc((2 * b + c) / 3), (j + 2) * 2);
  }
  return output;
}
