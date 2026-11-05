/**
 * Tests for analysis job lifecycle.
 *
 * These tests require a live PostgreSQL database. If the database is
 * not available, all tests in this file are skipped (not failed).
 * Set TEST_DATABASE_URL to point at a test database.
 */
import request from 'supertest';
import { PrismaClient } from '@prisma/client';
import { createApp } from '../src/app.js';

const TEST_DB_URL = process.env.TEST_DATABASE_URL || '';
const prisma = new PrismaClient({
  datasources: { db: { url: TEST_DB_URL || process.env.DATABASE_URL } },
});

let dbAvailable = false;
let testUserId: string;
let testImageId: string;

beforeAll(async () => {
  // Check if database is available
  try {
    await prisma.$connect();
    await prisma.$queryRaw`SELECT 1`;
    dbAvailable = true;

    // Create a test user
    const user = await prisma.user.create({
      data: { email: `test-${Date.now()}@pinithub.test`, name: 'Test User' },
    });
    testUserId = user.id;

    // Create a test image
    const image = await prisma.image.create({
      data: {
        ownerId: testUserId,
        role: 'SUSPECT',
        status: 'STORED',
        originalFilename: 'test.jpg',
        mimeType: 'image/jpeg',
        sizeBytes: BigInt(1024),
        sha256: `test-hash-${Date.now()}`,
        storagePath: `${testUserId}/image/test.jpg`,
      },
    });
    testImageId = image.id;
  } catch {
    dbAvailable = false;
  }
}, 10000);

afterAll(async () => {
  if (dbAvailable) {
    // Clean up test data
    try {
      await prisma.analysis.deleteMany({ where: { ownerId: testUserId } });
      await prisma.image.deleteMany({ where: { ownerId: testUserId } });
      await prisma.user.delete({ where: { id: testUserId } });
    } catch {
      // ignore cleanup errors
    }
  }
  await prisma.$disconnect();
});

const conditionalDescribe = dbAvailable ? describe : describe.skip;

conditionalDescribe('Analysis job lifecycle', () => {
  const app = createApp();

  it('creates an analysis and queues a job', async () => {
    const res = await request(app)
      .post('/v1/analyses')
      .set('X-Owner-Id', testUserId)
      .send({
        imageId: testImageId,
        type: 'METADATA_EXIF',
      });

    expect(res.status).toBe(201);
    expect(res.body.analysis).toBeDefined();
    expect(res.body.analysis.status).toBe('QUEUED');
    expect(res.body.analysis.verdict).toBeNull();
    expect(res.body.analysis.confidence).toBeNull();
    // No fake forensic results
  });

  it('lists analyses', async () => {
    const res = await request(app)
      .get('/v1/analyses?page=1&pageSize=10')
      .set('X-Owner-Id', testUserId);

    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('items');
    expect(res.body).toHaveProperty('total');
    expect(Array.isArray(res.body.items)).toBe(true);
  });

  it('returns 404 for non-existent analysis', async () => {
    const res = await request(app)
      .get('/v1/analyses/00000000-0000-0000-0000-000000000000')
      .set('X-Owner-Id', testUserId);

    expect(res.status).toBe(404);
    expect(res.body.error.code).toBe('NOT_FOUND');
  });
});
