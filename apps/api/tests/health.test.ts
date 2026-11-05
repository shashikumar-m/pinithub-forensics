/**
 * Tests for health and readiness endpoints.
 * These do NOT require a database connection — health is a liveness
 * check and ready degrades gracefully.
 */
import request from 'supertest';
import { createApp } from '../src/app.js';

const app = createApp();

describe('GET /v1/health', () => {
  it('returns 200 with correct shape', async () => {
    const res = await request(app).get('/v1/health');

    expect(res.status).toBe(200);
    expect(res.body).toEqual({
      status: 'ok',
      service: 'pinithub-api',
      version: '0.1.0',
      timestamp: expect.any(String),
    });
  });

  it('includes a valid ISO timestamp', async () => {
    const res = await request(app).get('/v1/health');
    const ts = new Date(res.body.timestamp);
    expect(ts.getTime()).not.toBeNaN();
  });
});

describe('GET /v1/ready', () => {
  it('returns a ready response with check structure', async () => {
    const res = await request(app).get('/v1/ready');

    // Status may be 200 or 503 depending on whether DB/forensics are up
    expect([200, 503]).toContain(res.status);
    expect(res.body).toHaveProperty('status');
    expect(res.body).toHaveProperty('service', 'pinithub-api');
    expect(res.body).toHaveProperty('checks');
    expect(res.body.checks).toHaveProperty('database');
    expect(res.body.checks).toHaveProperty('storage');
    expect(res.body.checks).toHaveProperty('forensics');
    expect(res.body).toHaveProperty('timestamp');
  });
});
