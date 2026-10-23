/** LAN and cloud bridges share the same bounded PCM framing. No audio is logged. */
export function encodePcm(generation: number, sequence: number, pcm: Buffer): Buffer {
  if (!Number.isInteger(generation) || generation < 1 || generation > 0xffffffff ||
      !Number.isInteger(sequence) || sequence < 0 || sequence > 0xffffffff ||
      pcm.length === 0 || pcm.length % 2 !== 0 || pcm.length > 960)
    throw new Error('Invalid PCM frame');
  const packet = Buffer.alloc(12 + pcm.length);
  packet.writeUInt32LE(generation, 0);
  packet.writeUInt32LE(sequence, 4);
  packet.writeUInt16LE(pcm.length / 2, 8);
  packet.writeUInt16LE(0, 10);
  pcm.copy(packet, 12);
  return packet;
}

export function decodePcm(packet: Buffer, maxPayload: 640 | 960): {
  generation: number; sequence: number; pcm: Buffer;
} {
  if (packet.length < 14 || packet.length > 12 + maxPayload ||
      packet.readUInt16LE(10) !== 0 ||
      packet.readUInt16LE(8) * 2 !== packet.length - 12 ||
      packet.readUInt32LE(0) === 0)
    throw new Error('Invalid PCM frame');
  return {
    generation: packet.readUInt32LE(0),
    sequence: packet.readUInt32LE(4),
    pcm: packet.subarray(12),
  };
}
