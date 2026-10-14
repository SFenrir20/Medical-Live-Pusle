const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
export type Profile = { id: string; status: 'pending' | 'approved'; accounts: string[] };
export type Shift = {
 id: string; account_id: string; user_id: string; started_at: string;
 ended_at: string | null; end_reason: 'manual' | 'handover' | null; closed_by: string | null;
};
export type ShiftHistory = { items: Shift[]; next_offset: number | null };
export class ApiError extends Error {
 constructor(message: string, public status: number) { super(message); }
}
async function authenticated(path: string, token: string | null, init?: RequestInit) {
 if (!token) throw new Error('Inicia sesión para continuar.');
 const controller = new AbortController();
 const timer = setTimeout(() => controller.abort(), 20000);
 let response: Response;
 try {
   response = await fetch(`${API_URL}${path}`, {
     ...init, signal: controller.signal,
     headers: { ...init?.headers, Authorization: `Bearer ${token}` },
   });
 } catch {
   throw new Error('No se recibió respuesta del servidor. Comprueba tu conexión y reintenta.');
 } finally { clearTimeout(timer); }
 if (!response.ok) {
   const body = await response.json().catch(() => null);
   throw new ApiError(response.status === 401 ? 'Tu sesión venció. Vuelve a iniciar sesión.'
     : typeof body?.detail === 'string' ? body.detail
     : 'No se pudo consultar el servidor. Inténtalo otra vez.', response.status);
 }
 return response.json();
}
export async function getProfile(token: string | null): Promise<Profile> {
 return authenticated('/v1/me', token);
}
export async function checkIn(account_id: string, token: string | null, key: string,
 replace_shift_id: string | null = null): Promise<Shift> {
 return authenticated('/v1/shifts/check-in', token, { method: 'POST',
   headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
   body: JSON.stringify({ account_id, replace_shift_id }) });
}
export async function checkOut(account_id: string, shift_id: string, token: string | null,
 key: string): Promise<Shift> {
 return authenticated(`/v1/shifts/check-out?account_id=${encodeURIComponent(account_id)}&shift_id=${encodeURIComponent(shift_id)}`,
   token, { method: 'POST', headers: { 'Idempotency-Key': key } });
}
export async function getActiveShift(account_id: string, token: string | null): Promise<Shift | null> {
 return authenticated(`/v1/shifts/active?account_id=${encodeURIComponent(account_id)}`, token);
}
export async function getShiftHistory(token: string | null, offset = 0): Promise<ShiftHistory> {
 return authenticated(`/v1/shifts/history?offset=${offset}`, token);
}

export const staffRequest = authenticated;
