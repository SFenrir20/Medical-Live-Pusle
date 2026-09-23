const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
export type Profile = { id: string; status: 'pending' | 'approved'; accounts: string[] };
async function authenticated(path: string, token: string | null, init?: RequestInit) {
 if (!token) throw new Error('Inicia sesión para continuar.');
 const response = await fetch(`${API_URL}${path}`, {
   ...init, headers: { ...init?.headers, Authorization: `Bearer ${token}` },
 });
 if (!response.ok) throw new Error(response.status === 401
   ? 'Tu sesión venció. Vuelve a iniciar sesión.' : 'No se pudo consultar el servidor. Inténtalo otra vez.');
 return response.json();
}
export async function getProfile(token: string | null): Promise<Profile> {
 return authenticated('/v1/me', token);
}
export async function checkIn(account_id: string, token: string | null) {
 return authenticated('/v1/shifts/check-in', token, { method: 'POST',
   headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `${Date.now()}-${Math.random()}` },
   body: JSON.stringify({ account_id }) });
}
export async function getActiveShift(account_id: string, token: string | null) {
 return authenticated(`/v1/shifts/active?account_id=${encodeURIComponent(account_id)}`, token);
}
