// Supabase Deno Edge Function: redeem-reward
// Handles secure server-side validation and transactional deduction of points for rewards or donations.
// Location: supabase/functions/redeem-reward/index.ts

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ALLOWED_ORIGINS = [
  "https://helpon.netlify.app",   // Production Netlify deployment
  "https://soulkingpk.github.io", // GitHub Pages
  "http://localhost:8000",         // Local web server
  "http://127.0.0.1:8000",
  "http://localhost:5500",         // Common Live Server port
  "http://127.0.0.1:5500"
];

function getCorsHeaders(req: Request) {
  const origin = req.headers.get("Origin") || "";
  const allowed = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
  };
}

serve(async (req: Request) => {
  const corsHeaders = getCorsHeaders(req);

  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    // 1. Authenticate caller (verify JWT)
    const authHeader = req.headers.get("Authorization");
    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return new Response(JSON.stringify({ error: "Unauthorized — no session token found." }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 401,
      });
    }

    const supabaseAnon = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_ANON_KEY") ?? "",
      { global: { headers: { Authorization: authHeader } } }
    );
    const { data: { user }, error: authError } = await supabaseAnon.auth.getUser();
    if (authError || !user) {
      return new Response(JSON.stringify({ error: "Unauthorized — invalid session token." }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 401,
      });
    }

    // 2. Parse and validate input
    const { rewardId } = await req.json();
    if (!rewardId) {
      return new Response(JSON.stringify({ error: "Missing rewardId in request body." }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 400,
      });
    }

    // 3. Determine voucher prefix based on the reward type
    // Donation projects get "DONATE-" prefix, vouchers get "REDEEM-"
    const DONATION_IDS = ['children_foundation', 'elder_care', 'disaster_relief', 'animal_welfare'];
    const prefix = DONATION_IDS.includes(rewardId) ? 'DONATE-' : 'REDEEM-';

    // Generate secure random alphanumeric voucher code using Web Crypto CSPRNG
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const arr = new Uint8Array(8);
    crypto.getRandomValues(arr);
    const secureCode = Array.from(arr).map(b => chars[b % chars.length]).join('');
    const voucherCode = `${prefix}${secureCode}`;

    // 4. Invoke the secure database function using the service role key to ensure atomic execution
    const supabaseAdmin = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
      { auth: { persistSession: false } }
    );

    const { data: result, error: rpcError } = await supabaseAdmin.rpc('redeem_reward_secure', {
      p_user_id: user.id,
      p_reward_id: rewardId,
      p_voucher_code: voucherCode
    });

    if (rpcError) {
      console.error("[redeem-reward] RPC call failed:", rpcError);
      return new Response(JSON.stringify({ error: "Database transaction failed: " + rpcError.message }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 500,
      });
    }

    if (!result || !result.success) {
      return new Response(JSON.stringify({ error: result?.error || "Redemption validation failed." }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 400,
      });
    }

    return new Response(
      JSON.stringify({
        success: true,
        voucherCode: result.voucher_code,
        newBalance: result.new_balance
      }),
      {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 200,
      }
    );

  } catch (err: any) {
    console.error("[redeem-reward] Unhandled error:", err);
    return new Response(JSON.stringify({ error: err.message }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
      status: 500,
    });
  }
});
