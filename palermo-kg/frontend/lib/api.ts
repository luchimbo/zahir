export async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.error ?? "No se pudo consultar la API");
  }
  return payload;
}
