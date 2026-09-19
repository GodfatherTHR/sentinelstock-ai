import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import type { User } from "@supabase/supabase-js";

/**
 * Resolve the signed-in operator on the server.
 *
 * This runs in the Node runtime from a server component, so it validates the session
 * against Supabase instead of trusting a cookie's presence. Server components cannot
 * write cookies, so token refresh stays with the browser client (lib/supabase-browser).
 */
export async function getServerUser(): Promise<User | null> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key || url.includes("your-project")) return null;

  const cookieStore = await cookies();
  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll() {
        // No-op: route handlers and server actions are the only places allowed to set cookies.
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
}
