import {test} from 'node:test';
import assert from 'node:assert/strict';
import {decodePcm, encodePcm} from '../protocol.js';

test('known little endian signed samples survive framing', () => {
  const pcm = Buffer.from([0, 128, 255, 127, 0, 0]);
  const packet = encodePcm(7, 9, pcm);
  assert.deepEqual([...packet.subarray(0, 12)], [7,0,0,0,9,0,0,0,3,0,0,0]);
  const frame = decodePcm(packet, 960);
  assert.equal(frame.generation, 7);
  assert.equal(frame.sequence, 9);
  assert.equal(frame.pcm.readInt16LE(0), -32768);
  assert.equal(frame.pcm.readInt16LE(2), 32767);
});

test('truncated, odd, inconsistent and oversized PCM is rejected', () => {
  for (const bad of [Buffer.alloc(2), Buffer.alloc(13), encodePcm(1, 0, Buffer.alloc(960))])
    assert.throws(() => decodePcm(bad, 640));
  const bad = encodePcm(1, 0, Buffer.alloc(20));
  bad.writeUInt16LE(2, 8);
  assert.throws(() => decodePcm(bad, 960));
  assert.throws(() => encodePcm(1, 0, Buffer.alloc(962)));
  assert.throws(() => encodePcm(1, 0, Buffer.alloc(3)));
});
