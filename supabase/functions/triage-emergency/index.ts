// Supabase Deno Edge Function: triage-emergency
// Performs AI triage analysis using OpenAI Vision API.
// Location: supabase/functions/triage-emergency/index.ts
//
// Security hardening (2026-06-01):
//   - Added JWT authentication — unauthenticated requests are rejected
//   - Added ownership verification — only the SOS creator can triage their emergency
//   - CORS restricted to production domain allowlist

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// CORS — restrict to your production domains only
const ALLOWED_ORIGINS = [
  "https://helpon.netlify.app",   // Update to your actual Netlify URL
  "https://soulkingpk.github.io", // GitHub Pages deployment
  "http://localhost:8000",         // Local dev server
  "http://127.0.0.1:8000"         // Local dev alternate
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
    // ── Step 1: Authenticate the caller ──────────────────────────────────────
    const authHeader = req.headers.get("Authorization");
    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return new Response(JSON.stringify({ error: "Unauthorized — no token" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 401,
      });
    }

    // Verify the JWT against Supabase auth
    const supabaseAnon = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_ANON_KEY") ?? "",
      { global: { headers: { Authorization: authHeader } } }
    );
    const { data: { user }, error: authError } = await supabaseAnon.auth.getUser();
    if (authError || !user) {
      return new Response(JSON.stringify({ error: "Unauthorized — invalid token" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 401,
      });
    }

    // ── Step 2: Parse and validate input ─────────────────────────────────────
    const { emergencyId, imageUrl, description } = await req.json();
    if (!emergencyId) {
      return new Response(JSON.stringify({ error: "Missing emergencyId" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 400,
      });
    }

    // ── Step 3: Verify the emergency belongs to the requesting user ───────────
    // This prevents one user from manipulating triage results for another's SOS.
    const supabaseAdmin = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
      { auth: { persistSession: false } }
    );

    const { data: emergency, error: fetchError } = await supabaseAdmin
      .from("emergencies")
      .select("user_id")
      .eq("id", emergencyId)
      .single();

    if (fetchError || !emergency) {
      return new Response(JSON.stringify({ error: "Emergency not found" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 404,
      });
    }

    if (emergency.user_id !== user.id) {
      return new Response(JSON.stringify({ error: "Forbidden — not your emergency" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 403,
      });
    }

    // ── Step 4: Run AI triage ──────────────────────────────────────────────────
    const openAiApiKey = Deno.env.get("OPENAI_API_KEY");
    let severity = "medium";
    let aiAnalysis: any = { status: "simulated", notes: "No OpenAI API key configured." };

    if (openAiApiKey) {
      const messages: any[] = [
        {
          role: "system",
          content: "You are an emergency dispatcher AI. Analyze the user's emergency description and/or image. Classify the emergency severity as 'high' (immediate life threat, fire, bleeding, unconsciousness), 'medium' (urgent but non-life-threatening medical/safety help needed), or 'low' (minor help, road blockage, information assistance). Return a JSON object with format: {\"severity\": \"high\" | \"medium\" | \"low\", \"analysis\": \"brief description of findings\"}."
        },
        {
          role: "user",
          content: [
            { type: "text", text: `Description: ${description || "No description provided."}` }
          ]
        }
      ];

      // Add image if provided
      if (imageUrl) {
        messages[1].content.push({
          type: "image_url",
          image_url: { url: imageUrl }
        });
      }

      const response = await fetch("https://api.openai.com/v1/chat/completions", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${openAiApiKey}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          model: "gpt-4o-mini",
          messages: messages,
          response_format: { type: "json_object" }
        })
      });

      if (response.ok) {
        const result = await response.json();
        const responseData = JSON.parse(result.choices[0].message.content.trim());
        severity = responseData.severity || "medium";
        aiAnalysis = {
          status: "completed",
          analysis: responseData.analysis,
          model: "gpt-4o-mini"
        };
      } else {
        console.error("OpenAI request failed:", await response.text());
        // Fall through to keyword heuristics
        aiAnalysis = { status: "openai_failed", notes: "Fell back to keyword heuristics." };
      }
    }

    // Keyword fallback (when no OpenAI key OR OpenAI failed)
    // CRITICAL: High-severity terms must be evaluated first and independently.
    // The original if/else-if chain allowed a low-severity keyword (e.g. 'dog')
    // to prevent a high-severity keyword ('bleed') from being matched if the
    // low branch was checked first. We now use an explicit priority cascade:
    //   HIGH → checked unconditionally first
    //   LOW  → only applied if no HIGH match was found
    //   MEDIUM is the safe default
    if (aiAnalysis.status !== "completed") {
      const text = (description || "").toLowerCase();

      const HIGH_SEVERITY_TERMS = [
        "heart attack", "cardiac", "chest pain", "chest", "heart",
        "bleed", "blood", "hemorrhage",
        "unconscious", "unresponsive", "not breathing",
        "chok", "choking", "breath", "breathing",
        "fire", "burning", "smoke",
        "accident", "crash", "collision",
        "dying", "dead", "overdose", "poison",
        "stroke", "seizure", "convuls",
        "drown", "gun", "stab", "wound"
      ];

      const LOW_SEVERITY_TERMS = [
        "flat tire", "tyre", "tire",
        "lost", "directions",
        "block", "road block", "traffic",
        "dog", "cat", "animal",
        "locked out", "car trouble"
      ];

      // Evaluate HIGH first — if any high-severity term matches, stop immediately.
      const isHigh = HIGH_SEVERITY_TERMS.some(term => text.includes(term));
      if (isHigh) {
        severity = "high";
      } else {
        // Only check LOW if there was no high-severity match.
        const isLow = LOW_SEVERITY_TERMS.some(term => text.includes(term));
        if (isLow) severity = "low";
        // else: severity remains "medium" (the safe default)
      }

      if (aiAnalysis.status !== "openai_failed") {
        aiAnalysis = { status: "simulated_local", notes: "Priority-ordered keyword heuristics applied." };
      }
    }

    // ── Step 5: Write result to DB using admin client ─────────────────────────
    const { error: updateError } = await supabaseAdmin
      .from("emergencies")
      .update({ severity, ai_analysis: aiAnalysis })
      .eq("id", emergencyId);

    if (updateError) throw updateError;

    return new Response(
      JSON.stringify({ success: true, severity, aiAnalysis }),
      {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 200,
      }
    );

  } catch (err: any) {
    console.error("[triage-emergency] Unhandled error:", err);
    return new Response(JSON.stringify({ error: err.message }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
      status: 500,
    });
  }
});
