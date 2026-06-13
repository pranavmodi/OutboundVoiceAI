import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Paths that bypass the outbound caller's session check. The /backfill area
// is an independent agent (see docs/cancellation-backfill/architecture.md) —
// it does not share auth with the outbound caller and must be reachable
// without the outbound backend running.
const PUBLIC_PATHS = ["/login", "/backfill", "/dev"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public paths and static assets
  if (
    PUBLIC_PATHS.some((p) => pathname.startsWith(p)) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon")
  ) {
    return NextResponse.next();
  }

  // Check for session cookie
  const session = request.cookies.get("session")?.value;
  if (!session) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Basic format check (nonce.expiry.sig)
  const parts = session.split(".");
  if (parts.length !== 3) {
    const response = NextResponse.redirect(new URL("/login", request.url));
    response.cookies.delete("session");
    return response;
  }

  // Check expiry client-side (server re-validates via /api/auth/check)
  try {
    const expires = parseInt(parts[1], 10);
    if (expires < Math.floor(Date.now() / 1000)) {
      const response = NextResponse.redirect(new URL("/login", request.url));
      response.cookies.delete("session");
      return response;
    }
  } catch {
    const response = NextResponse.redirect(new URL("/login", request.url));
    response.cookies.delete("session");
    return response;
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
