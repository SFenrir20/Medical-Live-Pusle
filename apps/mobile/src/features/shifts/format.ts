export function shiftTime(value: string) {
 return new Date(value).toLocaleString('es-PE', {
   timeZone: 'America/Lima', day: '2-digit', month: '2-digit', year: 'numeric',
   hour: '2-digit', minute: '2-digit', second: '2-digit',
 });
}
export function shiftDuration(start: string, end: string) {
 const minutes = Math.max(0, Math.floor((Date.parse(end) - Date.parse(start)) / 60000));
 return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}
