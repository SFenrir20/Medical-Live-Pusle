import { act, renderHook } from '@testing-library/react-native';
import { useEffect, useState } from 'react';
import { useSession } from '../features/auth/session';

let mockSessionId = 'session-a';
let mockTokenValue = 'token-a';
const mockGetToken = jest.fn(() => Promise.resolve(mockTokenValue));
jest.mock('@clerk/expo', () => ({
 // Reproduce the SDK: a new getToken function on every render.
 useAuth: () => ({ isLoaded: true, isSignedIn: true, sessionId: mockSessionId,
   getToken: () => mockGetToken() }),
 useClerk: () => ({ signOut: jest.fn() }),
 useUser: () => ({ user: { firstName: 'Ana' } }),
}));

beforeEach(() => { jest.clearAllMocks(); mockSessionId = 'session-a'; mockTokenValue = 'token-a'; });

test('Clerk rerenders do not restart token-dependent effects', async () => {
 const calls = jest.fn();
 const { result, rerender } = renderHook(() => {
   const session = useSession();
   const { getToken } = session;
   const [value, setValue] = useState<string | null>('');
   useEffect(() => { calls(); void getToken().then(setValue); }, [getToken]);
   return { ...session, value };
 });
 await act(async () => {});
 const firstGetToken = result.current.getToken;
 rerender({}); rerender({});
 expect(result.current.value).toBe('token-a');
 expect(result.current.getToken).toBe(firstGetToken);
 expect(calls).toHaveBeenCalledTimes(1);
 expect(mockGetToken).toHaveBeenCalledTimes(1);
 // A stable function must still obtain the latest token, never reuse a saved JWT.
 mockTokenValue = 'token-refreshed'; rerender({});
 await expect(result.current.getToken()).resolves.toBe('token-refreshed');
});

test('switching Clerk session invalidates old callers and refreshes effects', async () => {
 const { result, rerender } = renderHook(() => useSession());
 const previous = result.current.getToken;
 mockSessionId = 'session-b'; mockTokenValue = 'token-b'; rerender({});
 expect(result.current.getToken).not.toBe(previous);
 await expect(previous()).resolves.toBeNull();
 await expect(result.current.getToken()).resolves.toBe('token-b');
});
