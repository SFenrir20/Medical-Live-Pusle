import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Text as MockText, View as MockView } from 'react-native';
import Home from '../../app/home';
import Login from '../../app/index';
import { getProfile, checkIn } from '../services/api';

const mockToken = jest.fn().mockResolvedValue('signed-token');
const mockLogout = jest.fn().mockResolvedValue(undefined);
const mockHosted = jest.fn().mockResolvedValue({});
let mockSignedIn = false;
jest.mock('@clerk/expo/hosted-auth', () => ({ useHostedAuth: () => ({ startHostedAuth: mockHosted }) }));
jest.mock('../features/auth/session', () => ({ useSession: () => ({ ready: true, signedIn: mockSignedIn, getToken: mockToken, logout: mockLogout, name: 'Ana' }) }));
jest.mock('expo-router', () => ({
 Redirect: ({ href }: { href: string }) => <MockText>redirect:{href}</MockText>,
 Link: ({ children }: { children: React.ReactNode }) => <MockText>{children}</MockText>,
}));
jest.mock('react-native-safe-area-context', () => ({ SafeAreaView: ({ children }: { children: React.ReactNode }) => <MockView>{children}</MockView> }));
const mockFetch = jest.fn();
beforeEach(() => {
 jest.clearAllMocks(); mockSignedIn = false; global.fetch = mockFetch;
 mockFetch.mockResolvedValue({ ok: true, json: async () => ({ id: 'user_1', status: 'pending', accounts: [] }) });
});

test('protected screen redirects without requesting data', () => {
 render(<Home />); expect(screen.getByText('redirect:/')).toBeTruthy(); expect(mockFetch).not.toHaveBeenCalled();
});
test('login and signup open the real Clerk boundary', async () => {
 render(<Login />);
 fireEvent.press(screen.getByText('INICIAR SESIÓN'));
 await waitFor(() => expect(mockHosted).toHaveBeenCalledWith({ mode: 'sign-in' }));
 await waitFor(() => expect(screen.getByText('CREAR CUENTA')).toBeTruthy());
 fireEvent.press(screen.getByText('CREAR CUENTA'));
 await waitFor(() => expect(mockHosted).toHaveBeenCalledWith({ mode: 'sign-up' }));
});
test('new user sees approval status and bearer token is sent', async () => {
 mockSignedIn = true; render(<Home />);
 await screen.findByText('Acceso pendiente de aprobación');
 expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/v1/me'), expect.objectContaining({ headers: { Authorization: 'Bearer signed-token' } }));
 expect(screen.queryByText('@medical.cirugias')).toBeNull();
 fireEvent.press(screen.getByText('Cerrar sesión'));
 expect(mockLogout).toHaveBeenCalled();
});
test('only assigned TikTok accounts appear', async () => {
 mockSignedIn = true;
 mockFetch.mockResolvedValue({ ok: true, json: async () => ({ id: 'user_1', status: 'approved', accounts: ['medical-2'] }) });
 render(<Home />);
 await screen.findByText('@medical.cirugias2');
 expect(screen.queryByText('@medical.cirugias')).toBeNull();
});
test('missing token cannot call API or check in', async () => {
 await expect(getProfile(null)).rejects.toThrow('Inicia sesión');
 await expect(checkIn('medical', null)).rejects.toThrow('Inicia sesión');
 expect(mockFetch).not.toHaveBeenCalled();
});
test('API failure shows retry instead of approval or fake data', async () => {
 mockSignedIn = true; mockFetch.mockResolvedValue({ ok: false, status: 503 });
 render(<Home />); await screen.findByText('REINTENTAR');
 expect(screen.queryByText('Acceso pendiente de aprobación')).toBeNull();
});
