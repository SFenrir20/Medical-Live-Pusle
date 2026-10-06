import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { AppState, AppStateStatus, Text as MockText, View as MockView } from 'react-native';
import Home from '../../app/home';
import Login from '../../app/index';
import History from '../../app/history';
import { getProfile, checkIn } from '../services/api';

const mockToken = jest.fn().mockResolvedValue('signed-token');
const mockLogout = jest.fn().mockResolvedValue(undefined);
const mockHosted = jest.fn().mockResolvedValue({});
let mockSignedIn = false;
jest.mock('@clerk/expo/hosted-auth', () => ({ useHostedAuth: () => ({ startHostedAuth: mockHosted }) }));
jest.mock('../features/auth/session', () => ({ useSession: () => ({ ready: true, signedIn: mockSignedIn, getToken: mockToken, logout: mockLogout, name: 'Ana' }) }));
jest.mock('expo-router', () => ({
 useFocusEffect: (callback: () => void) => {
   const React = jest.requireActual('react');
   React.useEffect(callback, [callback]);
 },
 Redirect: ({ href }: { href: string }) => <MockText>redirect:{href}</MockText>,
 Link: ({ children }: { children: React.ReactNode }) => <MockText>{children}</MockText>,
}));
jest.mock('react-native-safe-area-context', () => ({ SafeAreaView: ({ children }: { children: React.ReactNode }) => <MockView>{children}</MockView> }));
const mockFetch = jest.fn();
let mockAppStateListener: ((state: AppStateStatus) => void) | undefined;
jest.mock('expo-crypto', () => ({ getRandomBytes: () => new Uint8Array(16).fill(7) }));
beforeEach(() => {
 jest.clearAllMocks();
 jest.spyOn(AppState, 'addEventListener').mockImplementation((_event, listener) => {
   mockAppStateListener = listener; return { remove: jest.fn() };
 });
 mockFetch.mockReset(); mockSignedIn = false; global.fetch = mockFetch;
 mockFetch.mockImplementation(async (url: string) => ({ ok: true, json: async () => url.includes('/v1/me') ? { id: 'user_1', status: 'approved', accounts: ['medical', 'medical-2'] } : null }));
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
test('new user can choose either TikTok account without approval', async () => {
 mockSignedIn = true; render(<Home />);
 await screen.findByText('¿En qué cuenta harás el LIVE?');
 const first = screen.getByRole('radio', { name: '@medical.cirugias' });
 const second = screen.getByRole('radio', { name: '@medical.cirugias2' });
 expect(first.props.accessibilityState.checked).toBe(false);
 expect(second.props.accessibilityState.checked).toBe(false);
 fireEvent.press(first);
 expect(screen.getByRole('radio', { name: '@medical.cirugias' }).props.accessibilityState.checked).toBe(true);
 fireEvent.press(second);
 expect(screen.getByRole('radio', { name: '@medical.cirugias' }).props.accessibilityState.checked).toBe(false);
 expect(screen.getByRole('radio', { name: '@medical.cirugias2' }).props.accessibilityState.checked).toBe(true);
 await screen.findByText('MARCAR ENTRADA');
 expect(mockFetch.mock.calls.every(([, init]) => init.method !== 'POST')).toBe(true);
 expect(screen.queryByText('Acceso pendiente de aprobación')).toBeNull();
 expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/v1/me'), expect.objectContaining({ headers: { Authorization: 'Bearer signed-token' } }));
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
 await expect(checkIn('medical', null, 'key')).rejects.toThrow('Inicia sesión');
 expect(mockFetch).not.toHaveBeenCalled();
});
test('API failure shows retry instead of approval or fake data', async () => {
 mockSignedIn = true; mockFetch.mockResolvedValue({ ok: false, status: 503, json: async () => null });
 render(<Home />); await screen.findByText('REINTENTAR');
 expect(screen.queryByText('Acceso pendiente de aprobación')).toBeNull();
});


test('revoked user cannot select accounts or bypass server permissions', async () => {
 mockSignedIn = true;
 mockFetch.mockResolvedValue({ ok: true, json: async () => ({ id: 'user_1', status: 'pending', accounts: [] }) });
 render(<Home />);
 await screen.findByText('No hay cuentas disponibles');
 expect(screen.queryAllByRole('radio')).toHaveLength(0);
});

test('leaving the screen clears the account choice', async () => {
 mockSignedIn = true;
 const view = render(<Home />);
 fireEvent.press(await screen.findByRole('radio', { name: '@medical.cirugias2' }));
 view.unmount();
 render(<Home />);
 const radio = await screen.findByRole('radio', { name: '@medical.cirugias2' });
 expect(radio.props.accessibilityState.checked).toBe(false);
});

const openShift = { id: 'shift-1', account_id: 'medical', user_id: 'user_1',
 started_at: '2026-10-06T19:00:00+00:00', ended_at: null, end_reason: null, closed_by: null };
function server(initial: typeof openShift | null = null) {
 let active: any = initial;
 mockFetch.mockImplementation(async (url: string, init: RequestInit) => {
   if (url.includes('/v1/me')) return { ok: true, json: async () => ({ id: 'user_1', status: 'approved', accounts: ['medical', 'medical-2'] }) };
   if (url.includes('/active')) return { ok: true, json: async () => active };
   if (url.includes('/check-in')) {
     active = { ...openShift, account_id: JSON.parse(init.body as string).account_id };
     return { ok: true, json: async () => active };
   }
   if (url.includes('/check-out')) {
     active = null;
     return { ok: true, json: async () => ({ ...openShift, ended_at: '2026-10-06T22:00:00+00:00', end_reason: 'manual' }) };
   }
   throw new Error('Unexpected request');
 });
}
async function selectFirst() {
 mockSignedIn = true; render(<Home />);
 fireEvent.press(await screen.findByRole('radio', { name: '@medical.cirugias' }));
}
test('entry is explicit, persists after remount, and exit needs confirmation', async () => {
 server(); await selectFirst();
 fireEvent.press(await screen.findByText('MARCAR ENTRADA'));
 await screen.findByText('Tu turno está abierto');
 expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/check-in'), expect.objectContaining({ method: 'POST', body: JSON.stringify({ account_id: 'medical', replace_shift_id: null }) }));
 screen.unmount();
 await selectFirst();
 await screen.findByText('Tu turno está abierto');
 fireEvent.press(screen.getByText('MARCAR SALIDA'));
 expect(mockFetch.mock.calls.filter(([url]) => url.includes('/check-out'))).toHaveLength(0);
 fireEvent.press(screen.getByText('CONFIRMAR SALIDA'));
 await screen.findByText('MARCAR ENTRADA');
 expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('shift_id=shift-1'), expect.objectContaining({ method: 'POST' }));
});
test('handover explicitly identifies the observed turn', async () => {
 server({ ...openShift, user_id: 'another-user' }); await selectFirst();
 fireEvent.press(await screen.findByText('RELEVAR Y MARCAR ENTRADA'));
 expect(mockFetch.mock.calls.filter(([, init]) => init.method === 'POST')).toHaveLength(0);
 fireEvent.press(screen.getByText('CONFIRMAR RELEVO'));
 await screen.findByText('Tu turno está abierto');
 expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/check-in'), expect.objectContaining({ body: JSON.stringify({ account_id: 'medical', replace_shift_id: 'shift-1' }) }));
});
test('lost response retries with the same key and body', async () => {
 server(); await selectFirst();
 await screen.findByText('MARCAR ENTRADA');
 mockFetch.mockRejectedValueOnce(new Error('Conexión interrumpida'));
 fireEvent.press(screen.getByText('MARCAR ENTRADA'));
 fireEvent.press(await screen.findByText('REINTENTAR MARCACIÓN'));
 await screen.findByText('Tu turno está abierto');
 const posts = mockFetch.mock.calls.filter(([, init]) => init.method === 'POST');
 expect(posts).toHaveLength(2);
 expect(posts[0][0]).toEqual(posts[1][0]);
 expect(posts[0][1].body).toEqual(posts[1][1].body);
 expect(posts[0][1].headers).toEqual(posts[1][1].headers);
});
test('history displays persisted dates and automatic closure reason', async () => {
 mockSignedIn = true;
 mockFetch.mockResolvedValue({ ok: true, json: async () => ({ items: [{ ...openShift,
   ended_at: '2026-10-06T22:00:00+00:00', end_reason: 'handover' }], next_offset: null }) });
 render(<History />);
 await screen.findByText('Cierre automático por relevo');
 expect(screen.getByText('Duración: 3 h 0 min')).toBeTruthy();
 expect(screen.getByText('@medical.cirugias')).toBeTruthy();
});

test('a stale turn refreshes state without silently taking over', async () => {
 server(); await selectFirst();
 await screen.findByText('MARCAR ENTRADA');
 mockFetch.mockResolvedValueOnce({ ok: false, status: 409,
   json: async () => ({ detail: 'El turno cambió. Actualiza antes de marcar o relevar.' }) });
 fireEvent.press(screen.getByText('MARCAR ENTRADA'));
 await screen.findByText('El turno cambió. Actualiza antes de marcar o relevar.');
 await screen.findByText('MARCAR ENTRADA');
 expect(mockFetch.mock.calls.filter(([, init]) => init.method === 'POST')).toHaveLength(1);
 expect(screen.queryByText('REINTENTAR MARCACIÓN')).toBeNull();
});
test('double tap sends only one entry while the request is pending', async () => {
 server(); await selectFirst();
 const button = await screen.findByText('MARCAR ENTRADA');
 fireEvent.press(button); fireEvent.press(button);
 await screen.findByText('Tu turno está abierto');
 expect(mockFetch.mock.calls.filter(([, init]) => init.method === 'POST')).toHaveLength(1);
});

test('refresh keeps the turn and controls visible while the server responds', async () => {
 server(); await selectFirst();
 await screen.findByText('MARCAR ENTRADA');
 let respond!: (value: unknown) => void;
 mockFetch.mockImplementationOnce(() => new Promise(resolve => { respond = resolve; }));
 fireEvent.press(screen.getByText('ACTUALIZAR ESTADO'));
 await waitFor(() => expect(respond).toBeDefined());
 expect(screen.getByText('No hay un turno abierto en esta cuenta.')).toBeTruthy();
 expect(screen.getByText('MARCAR ENTRADA')).toBeTruthy();
 expect(screen.getByText('ACTUALIZAR ESTADO')).toBeTruthy();
 expect(screen.queryByLabelText('Consultando jornada')).toBeNull();
 await act(async () => { respond({ ok: true, json: async () => openShift }); });
 await screen.findByText('Tu turno está abierto');
 expect(screen.getByText('MARCAR SALIDA')).toBeTruthy();
});

test('background polling preserves the open confirmation and avoids overlapping reads', async () => {
 jest.useFakeTimers();
 try {
   server(openShift); await selectFirst();
   fireEvent.press(await screen.findByText('MARCAR SALIDA'));
   let respond!: (value: unknown) => void;
   mockFetch.mockImplementationOnce(() => new Promise(resolve => { respond = resolve; }));
   const count = mockFetch.mock.calls.length;
   await act(async () => { jest.advanceTimersByTime(30000); });
   expect(screen.getByText('CONFIRMAR SALIDA')).toBeTruthy();
   expect(screen.queryByLabelText('Consultando jornada')).toBeNull();
   // An AppState wakeup during this pending read must not start another one.
   await act(async () => { mockAppStateListener?.('active'); });
   expect(mockFetch).toHaveBeenCalledTimes(count + 1);
   await act(async () => { respond({ ok: true, json: async () => openShift }); });
   expect(screen.getByText('CONFIRMAR SALIDA')).toBeTruthy();
 } finally { jest.useRealTimers(); }
});
