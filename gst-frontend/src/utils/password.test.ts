import { describe, expect, it } from 'vitest';
import { validatePassword } from './password';

describe('validatePassword', () => {
  it('accepts a strong password', () => {
    expect(validatePassword('Secret123!')).toBeNull();
  });

  it('rejects weak passwords', () => {
    expect(validatePassword('short')).toBe('Password must be at least 8 characters');
    expect(validatePassword('secret123!')).toBe('Password must contain at least one uppercase letter');
    expect(validatePassword('SECRET123!')).toBe('Password must contain at least one lowercase letter');
    expect(validatePassword('SecretPass!')).toBe('Password must contain at least one number');
    expect(validatePassword('Secret123')).toBe('Password must contain at least one special character');
  });
});
