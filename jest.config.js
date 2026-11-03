process.env.DATABASE_URL = process.env.TEST_DATABASE_URL || 'file:./test.db';
process.env.NODE_ENV = 'test';
process.env.GEMINI_API_KEY = process.env.GEMINI_API_KEY || 'ci-mock-gemini-api-key';
process.env.PORT = process.env.PORT || '3000';
process.env.ENABLE_LEGACY_EXPRESS_ROUTES = process.env.ENABLE_LEGACY_EXPRESS_ROUTES || 'true';

module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/tests/**/*.test.ts'],
  moduleFileExtensions: ['ts', 'js', 'json', 'node'],
  clearMocks: true,
  restoreMocks: true,
  testTimeout: 20000,
  maxWorkers: 1,
};

