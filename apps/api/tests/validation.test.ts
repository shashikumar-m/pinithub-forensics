/**
 * Tests for API validation and error handling.
 * These do NOT require a database connection.
 */
import request from 'supertest';
import { createApp } from '../src/app.js';

const app = createApp();

describe('Error response format', () => {
  it('returns structured error for unknown routes', async () => {
    const res = await request(app).get('/v1/nonexistent');

    expect(res.status).toBe(404);
    expect(res.body).toHaveProperty('error');
    expect(res.body.error).toHaveProperty('code');
    expect(res.body.error).toHaveProperty('message');
  });
});

describe('POST /v1/analyses validation', () => {
  it('rejects missing body', async () => {
    const res = await request(app).post('/v1/analyses').send({});

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
    expect(res.body.error.details).toBeDefined();
  });

  it('rejects invalid imageId (not UUID)', async () => {
    const res = await request(app)
      .post('/v1/analyses')
      .send({
        imageId: 'not-a-uuid',
        type: 'METADATA_EXIF',
      });

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
  });

  it('rejects invalid analysis type', async () => {
    const res = await request(app)
      .post('/v1/analyses')
      .send({
        imageId: '550e8400-e29b-41d4-a716-446655440000',
        type: 'INVALID_TYPE',
      });

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
  });
});

describe('GET /v1/analyses/:id validation', () => {
  it('rejects non-UUID id', async () => {
    const res = await request(app).get('/v1/analyses/not-a-uuid');

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
  });
});

describe('GET /v1/analyses query validation', () => {
  it('accepts valid pagination', async () => {
    // Allow extra time for Prisma connection retries when DB is down
    const res = await request(app).get('/v1/analyses?page=1&pageSize=10');

    // May be 500 if DB is down, but should not be 400 (validation error)
    expect(res.status).not.toBe(400);
  }, 30000);

  it('rejects page below 1', async () => {
    const res = await request(app).get('/v1/analyses?page=0');

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('VALIDATION_ERROR');
  });
});
