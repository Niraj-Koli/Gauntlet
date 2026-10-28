// Liveness for container probes: the Next.js server is up (it doesn't check the API).
export function GET() {
  return Response.json({ status: "ok" });
}
