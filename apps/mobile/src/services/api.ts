const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

function uuid(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function checkIn(account_id: string) {
  const res = await fetch(`${API_URL}/v1/shifts/check-in`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": uuid(),
    },
    body: JSON.stringify({ account_id }),
  });
  if (!res.ok) throw new Error(`check-in failed: ${res.status}`);
  return res.json();
}

export async function getActiveShift(account_id: string, token: string) {
  const res = await fetch(`${API_URL}/v1/shifts/active?account_id=${account_id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("active shift failed");
  return res.json();
}
