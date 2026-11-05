/** @type {import('jest').Config} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src', '<rootDir>/tests'],
  testMatch: ['**/*.test.ts'],
  extensionsToTreatAsEsm: ['.ts'],
  moduleNameMapper: {
    '^@pinithub/shared$': '<rootDir>/../../packages/shared/src/index.ts',
    '^(\\.{1,2}/.*)\\.js$': '$1'
  },
  transform: {
    '^.+\\.ts$': [
      'ts-jest',
      {
        tsconfig: {
          module: 'commonjs',
          esModuleInterop: true,
          moduleResolution: 'node',
          target: 'ES2022',
          strict: true,
          skipLibCheck: true,
          isolatedModules: true,
          noUnusedLocals: false,
          noUnusedParameters: false
        },
        useESM: false
      }
    ]
  },
  transformIgnorePatterns: ['node_modules'],
  clearMocks: true,
  forceExit: true,
  setupFiles: ['<rootDir>/tests/setup.ts']
};
