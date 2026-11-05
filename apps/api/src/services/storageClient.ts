/**
 * Storage client abstraction.
 *
 * Uses Supabase Storage when fully configured (URL + service-role key).
 * Falls back to a local filesystem directory when Supabase is not
 * configured or when network connection to Supabase fails/resets.
 *
 * Always writes to local filesystem as an instant, zero-latency cache so
 * background workers and forensics tasks can access image bytes reliably.
 *
 * In both cases, storage paths are owner-scoped and private by default.
 */
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { getStorageConfig, isStorageConfigured } from '../config/storage.js';
import { getLogger } from '../config/logger.js';
import { generateStoragePath } from './storage.js';

export interface StorageResult {
  storagePath: string;
  bucket: string;
  /** Whether the storage backend is Supabase (true) or local (false) */
  backend: 'supabase' | 'local';
}

let cachedSupabaseClient: any = null;
async function getSupabaseAdminClient(url: string, key: string) {
  if (!cachedSupabaseClient) {
    const { createClient } = await import('@supabase/supabase-js');
    cachedSupabaseClient = createClient(url, key, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
  }
  return cachedSupabaseClient;
}

export class StorageClient {
  /**
   * Stores a file buffer in object storage.
   * Returns the storage path and bucket.
   *
   * Persists locally first (guaranteeing local availability for forensics jobs),
   * then syncs to Supabase Storage with retry & graceful fallback.
   */
  async store(
    bucketName: string,
    ownerId: string,
    imageId: string,
    filename: string,
    buffer: Buffer,
    mimeType: string,
  ): Promise<StorageResult> {
    const log = getLogger();
    const storagePath = generateStoragePath(ownerId, imageId, filename);

    // 1. Always store to local disk first
    const localResult = await this.storeLocal(bucketName, storagePath, buffer);

    // 2. If Supabase is configured, upload to remote Supabase Storage with retries
    if (isStorageConfigured()) {
      try {
        const remoteResult = await this.storeSupabaseWithRetry(bucketName, storagePath, buffer, mimeType, 2);
        return remoteResult;
      } catch (err: any) {
        log.warn(
          { err: err?.message || err, bucket: bucketName, path: storagePath },
          'Supabase remote upload encountered error; falling back to local storage',
        );
        return localResult;
      }
    }

    return localResult;
  }

  /**
   * Uploads to Supabase with exponential backoff retry for transient network/TLS resets.
   */
  private async storeSupabaseWithRetry(
    bucketName: string,
    storagePath: string,
    buffer: Buffer,
    mimeType: string,
    maxRetries = 2,
  ): Promise<StorageResult> {
    const log = getLogger();
    let lastError: any = null;

    for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
      try {
        return await this.storeSupabase(bucketName, storagePath, buffer, mimeType);
      } catch (err: any) {
        lastError = err;
        if (attempt <= maxRetries) {
          log.warn(
            { attempt, maxRetries, err: err?.message || err, path: storagePath },
            'Retrying Supabase upload after transient failure...',
          );
          await new Promise((resolve) => setTimeout(resolve, 300 * attempt));
        }
      }
    }

    throw lastError;
  }

  private async storeSupabase(
    bucketName: string,
    storagePath: string,
    buffer: Buffer,
    mimeType: string,
  ): Promise<StorageResult> {
    const log = getLogger();
    const config = getStorageConfig();

    const client = await getSupabaseAdminClient(config.url!, config.serviceRoleKey!);

    const { error } = await client.storage
      .from(bucketName)
      .upload(storagePath, buffer, {
        contentType: mimeType,
        upsert: true, // allow re-upload of same path (idempotent)
      });

    if (error) {
      log.error({ err: error, bucket: bucketName, path: storagePath }, 'Supabase storage upload failed');
      throw new Error(`Storage upload failed: ${error.message}`);
    }

    return { storagePath, bucket: bucketName, backend: 'supabase' };
  }

  private async storeLocal(
    bucketName: string,
    storagePath: string,
    buffer: Buffer,
  ): Promise<StorageResult> {
    const log = getLogger();
    // Local fallback directory (gitignored)
    const localRoot = path.resolve(process.cwd(), '.local-storage');
    const fullPath = path.join(localRoot, bucketName, storagePath);

    // Create parent directories
    await fs.mkdir(path.dirname(fullPath), { recursive: true });

    // Prevent path traversal — ensure the resolved path is inside the root
    const resolvedRoot = path.resolve(localRoot, bucketName);
    if (!fullPath.startsWith(resolvedRoot)) {
      throw new Error('Invalid storage path detected');
    }

    await fs.writeFile(fullPath, buffer);

    log.debug({ bucket: bucketName, path: storagePath }, 'Stored file locally');
    return { storagePath, bucket: bucketName, backend: 'local' };
  }

  /**
   * Retrieves a file buffer. Checks local filesystem first, falls back to Supabase.
   */
  async retrieve(bucketName: string, storagePath: string): Promise<Buffer> {
    const localRoot = path.resolve(process.cwd(), '.local-storage');
    const fullPath = path.join(localRoot, bucketName, storagePath);

    try {
      return await fs.readFile(fullPath);
    } catch {
      if (isStorageConfigured()) {
        const config = getStorageConfig();
        const client = await getSupabaseAdminClient(config.url!, config.serviceRoleKey!);
        const { data, error } = await client.storage.from(bucketName).download(storagePath);
        if (error || !data) {
          throw new Error(`Failed to retrieve file from storage: ${error?.message ?? 'Not found'}`);
        }
        const arrayBuf = await data.arrayBuffer();
        const buffer = Buffer.from(arrayBuf);
        try {
          await fs.mkdir(path.dirname(fullPath), { recursive: true });
          await fs.writeFile(fullPath, buffer);
        } catch {}
        return buffer;
      }
      throw new Error(`File not found: ${bucketName}/${storagePath}`);
    }
  }
}

// Singleton
let clientInstance: StorageClient | null = null;
export function getStorageClient(): StorageClient {
  if (!clientInstance) clientInstance = new StorageClient();
  return clientInstance;
}
