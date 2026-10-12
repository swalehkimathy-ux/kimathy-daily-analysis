const OWNER = "swalehkimathy-ux";
const REPOSITORY = "kimathy-daily-analysis";
const WORKFLOW = "daily-analysis.yml";
const REF = "main";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Max-Age": "86400",
};

function jsonResponse(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

function defaultSupabaseKey(legacyName: string, keyMapName: string): string {
  const legacy = Deno.env.get(legacyName) || "";
  if (legacy) return legacy;
  try {
    const keyMap = JSON.parse(Deno.env.get(keyMapName) || "{}");
    if (keyMap && typeof keyMap === "object") {
      return String(keyMap.default || Object.values(keyMap)[0] || "");
    }
  } catch {
    // Ignore an unavailable or malformed key map.
  }
  return "";
}

function supabaseHeaders(key: string): HeadersInit {
  const headers: Record<string, string> = {
    apikey: key,
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  // Current sb_secret keys are opaque API keys, not JWTs. Sending one as a
  // Bearer token causes an Invalid JWT response; legacy service-role keys are JWTs.
  if (!key.startsWith("sb_secret_")) {
    headers.Authorization = `Bearer ${key}`;
  }
  return headers;
}

async function serviceRpc(
  baseUrl: string,
  serviceKey: string,
  functionName: string,
  body: Record<string, unknown> = {},
): Promise<{ ok: boolean; status: number; data: unknown }> {
  const response = await fetch(`${baseUrl}/rest/v1/rpc/${functionName}`, {
    method: "POST",
    headers: supabaseHeaders(serviceKey),
    body: JSON.stringify(body),
  });
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // The caller handles an empty or malformed result as a failed RPC.
  }
  return { ok: response.ok, status: response.status, data };
}

async function releaseReservation(
  baseUrl: string,
  serviceKey: string,
  reservationId: string,
): Promise<void> {
  try {
    await serviceRpc(baseUrl, serviceKey, "kimathy_release_manual_run", {
      p_reservation_id: reservationId,
    });
  } catch {
    // Keep the database reservation/cooldown fail-closed if release is uncertain.
  }
}

Deno.serve(async (request: Request): Promise<Response> => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (request.method !== "POST") {
    return jsonResponse(405, { error: "Use the manual analysis button in the private app." });
  }

  const authorization = request.headers.get("Authorization") || "";
  if (!/^Bearer\s+\S+$/i.test(authorization)) {
    return jsonResponse(401, { error: "Sign in to the private dashboard first." });
  }

  const supabaseUrl = (Deno.env.get("SUPABASE_URL") || "").replace(/\/+$/, "");
  const anonKey = defaultSupabaseKey("SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEYS");
  const serviceKey = defaultSupabaseKey("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEYS");
  const githubToken = Deno.env.get("KIMATHY_GITHUB_TOKEN") || "";
  if (!supabaseUrl || !anonKey || !serviceKey || !githubToken) {
    return jsonResponse(503, { error: "The secure analysis trigger is not fully configured." });
  }

  // Verify that this signed-in Supabase user is the explicitly allowlisted owner.
  let authorizationResponse: Response;
  try {
    authorizationResponse = await fetch(`${supabaseUrl}/rest/v1/rpc/kimathy_is_authorized_user`, {
      method: "POST",
      headers: {
        apikey: anonKey,
        Authorization: authorization,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: "{}",
    });
  } catch {
    return jsonResponse(503, { error: "Could not verify the signed-in account." });
  }
  if (!authorizationResponse.ok) {
    return jsonResponse(403, { error: "This account is not authorized to request analysis." });
  }
  let authorized = false;
  try {
    authorized = (await authorizationResponse.json()) === true;
  } catch {
    authorized = false;
  }
  if (!authorized) {
    return jsonResponse(403, { error: "This account is not authorized to request analysis." });
  }

  // The SQL function locks a single row and records today's request before GitHub
  // is contacted, so two browser requests cannot race past the calendar-day limit.
  let reservation: { ok: boolean; status: number; data: unknown };
  try {
    reservation = await serviceRpc(supabaseUrl, serviceKey, "kimathy_reserve_manual_run");
  } catch {
    return jsonResponse(503, { error: "Could not check today's request limit." });
  }
  if (!reservation.ok || !reservation.data || typeof reservation.data !== "object") {
    return jsonResponse(503, { error: "Could not check today's request limit." });
  }
  const reserveData = reservation.data as Record<string, unknown>;
  if (reserveData.allowed !== true) {
    return jsonResponse(429, {
      error: reserveData.reason === "request_pending"
        ? "An analysis request is already being sent. Please wait a few minutes."
        : "Only one analysis request is allowed per Tanzania calendar day (EAT).",
      reason: reserveData.reason || "cooldown",
      next_allowed_at: reserveData.next_allowed_at || null,
    });
  }
  const reservationId = String(reserveData.reservation_id || "");
  if (!reservationId) {
    return jsonResponse(503, { error: "Could not secure the analysis request." });
  }

  let githubResponse: Response;
  try {
    githubResponse = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPOSITORY}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          Accept: "application/vnd.github+json",
          Authorization: `Bearer ${githubToken}`,
          "X-GitHub-Api-Version": "2026-03-10",
          "User-Agent": "Kimathy-private-analysis-app",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ref: REF,
          inputs: { confirm_requests: "true" },
        }),
      },
    );
  } catch {
    // A transport failure may happen after GitHub accepted the dispatch. Keep
    // the cooldown rather than risk a duplicate run.
    return jsonResponse(502, {
      error: "GitHub did not confirm the request. To prevent a duplicate run, today's request reservation remains in effect.",
      next_allowed_at: reserveData.next_allowed_at || null,
    });
  }

  if (githubResponse.status !== 204) {
    // The HTTP code is safe to surface; never log or return GitHub response
    // bodies, which may contain unnecessary repository/workflow diagnostics.
    console.warn("GitHub workflow dispatch response", { status: githubResponse.status });
    // A clear 4xx rejection means GitHub did not dispatch a run; undo only our
    // own reservation. Keep it on 5xx because acceptance is uncertain.
    if (githubResponse.status < 500) {
      await releaseReservation(supabaseUrl, serviceKey, reservationId);
    }
    return jsonResponse(502, {
      error: githubResponse.status < 500
        ? `GitHub rejected the secure dispatch (HTTP ${githubResponse.status}). The request limit was released; check the token's repository Actions permission and workflow setup.`
        : `GitHub could not confirm the dispatch (HTTP ${githubResponse.status}). To prevent a duplicate run, today's request reservation remains in effect.`,
      github_status: githubResponse.status,
      next_allowed_at: githubResponse.status < 500 ? null : reserveData.next_allowed_at || null,
    });
  }

  // Leave the short reservation intact until the workflow claims it. This
  // avoids a race where the run starts before the browser receives this reply.
  return jsonResponse(200, {
    ok: true,
    message: "Analysis requested. You can refresh this dashboard in a few minutes.",
    next_allowed_at: reserveData.next_allowed_at || null,
  });
});
