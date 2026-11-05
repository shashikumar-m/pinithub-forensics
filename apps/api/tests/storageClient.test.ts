import { StorageClient } from '../src/services/storageClient.js';
import { promises as fs } from 'node:fs';
import path from 'node:path';

describe('StorageClient resilience and fallback', () => {
  const client = new StorageClient();
  const testBucket = 'test-bucket';
  const testOwner = 'test-owner-123';
  const testImage = 'test-image-456';
  const testFilename = 'sample.jpg';
  const testBuffer = Buffer.from('pinithub fake image content 12345');

  afterAll(async () => {
    // Clean up test directory if created
    const testDir = path.resolve(process.cwd(), '.local-storage', testBucket);
    try {
      await fs.rm(testDir, { recursive: true, force: true });
    } catch {}
  });

  it('successfully saves to local storage and returns local backend on network failure/fallback', async () => {
    const result = await client.store(
      testBucket,
      testOwner,
      testImage,
      testFilename,
      testBuffer,
      'image/jpeg',
    );

    expect(result).toBeDefined();
    expect(result.bucket).toBe(testBucket);
    expect(result.storagePath).toBe(`${testOwner}/${testImage}/${testFilename}`);
    expect(['local', 'supabase']).toContain(result.backend);

    // Verify file actually exists on local filesystem
    const retrieved = await client.retrieve(testBucket, result.storagePath);
    expect(retrieved.toString()).toBe(testBuffer.toString());
  });
});

