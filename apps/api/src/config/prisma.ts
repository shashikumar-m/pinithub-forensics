/**
 * Prisma client singleton.
 *
 * Prevents connection exhaustion during hot-reload in development
 * by reusing the global instance.
 */
import { PrismaClient } from '@prisma/client';

let prismaInstance: PrismaClient | null = null;

export function getPrisma(): PrismaClient {
  if (!prismaInstance) {
    prismaInstance = new PrismaClient({
      log: process.env.NODE_ENV === 'development' ? ['warn', 'error'] : ['error'],
    });
  }
  return prismaInstance;
}

/**
 * Resets the cached Prisma instance (used in tests).
 */
export function resetPrisma(): void {
  prismaInstance = null;
}

/**
 * Tests database connectivity. Returns true/false rather than throwing.
 */
export async function checkDatabase(prisma?: PrismaClient): Promise<boolean> {
  const client = prisma ?? getPrisma();
  try {
    await client.$queryRaw`SELECT 1`;
    return true;
  } catch {
    return false;
  }
}
