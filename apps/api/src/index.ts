/**
 * Server entry point.
 *
 * Validates environment at startup, creates the Express app, and
 * starts listening. Fails fast if required configuration is missing.
 * Run with: npx tsx --env-file=../../.env src/index.ts
 */
import { createApp } from './app.js';
import { getEnv } from './config/env.js';
import { getLogger } from './config/logger.js';
import { getPrisma } from './config/prisma.js';

async function bootstrap() {
  // Validate environment — throws if config is invalid
  let env;
  try {
    env = getEnv();
  } catch (err) {
    // Logger may not be available yet if env validation fails before logger init
    console.error('Failed to start server: environment validation failed');
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
  }

  const log = getLogger();

  log.info(
    { nodeEnv: env.NODE_ENV, port: env.PORT, logLevel: env.LOG_LEVEL },
    'Starting PINITHUB API server...',
  );

  // Test database connection on startup (non-fatal if it fails —
  // the /v1/ready endpoint reports the real status)
  try {
    const prisma = getPrisma();
    await prisma.$connect();
    log.info('Database connection established');
  } catch (err) {
    log.warn({ err }, 'Database connection failed — server will start but /v1/ready will report degraded');
  }

  const app = createApp();
  const server = app.listen(env.PORT, () => {
    log.info({ port: env.PORT }, `PINITHUB API server listening on port ${env.PORT}`);
  });

  // Graceful shutdown
  const shutdown = async (signal: string) => {
    log.info({ signal }, 'Shutting down gracefully...');
    server.close();
    try {
      const prisma = getPrisma();
      await prisma.$disconnect();
      log.info('Database disconnected');
    } catch (err) {
      log.error({ err }, 'Error during database disconnect');
    }
    process.exit(0);
  };

  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));

  // Unhandled error handlers
  process.on('unhandledRejection', (reason) => {
    log.error({ reason }, 'Unhandled promise rejection');
  });
  process.on('uncaughtException', (err) => {
    log.error({ err }, 'Uncaught exception');
    process.exit(1);
  });
}

bootstrap().catch((err) => {
  console.error('Fatal error during bootstrap');
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
