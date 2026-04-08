-- HelpOn Supabase Hardening Migration --
-- Run this in your Supabase SQL Editor (https://supabase.com/dashboard/project/_/sql/new) --

-- 1. Create Error Logs Table (for Telemetry) --
CREATE TABLE IF NOT EXISTS public.error_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    message TEXT,
    source TEXT,
    lineno INTEGER,
    colno INTEGER,
    stack TEXT,
    type VARCHAR(50), -- 'exception', 'promise_rejection', etc.
    url TEXT,
    user_id UUID DEFAULT auth.uid(), -- Automatically link to auth'd user
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS for Error Logs --
ALTER TABLE public.error_logs ENABLE ROW LEVEL SECURITY;

-- Policy: Only allow authenticated users to INSERT error logs --
-- This prevents anonymous spam, but also logged-in users can't read others' logs --
CREATE POLICY "Allow public insert to error_logs" ON public.error_logs
    FOR INSERT TO authenticated WITH CHECK (true);

-- 2. Standardize Profiles RLS --
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Anyone can see basic profile info (needed for helpers count/list) --
CREATE POLICY "Profiles are viewable by everyone" ON public.profiles
    FOR SELECT USING (true);

-- Users can only update their own profile --
CREATE POLICY "Users can update own profile" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- 3. Hardening Emergencies Table --
-- Ensure columns exist before setting policies --
ALTER TABLE public.emergencies ADD COLUMN IF NOT EXISTS helper_id UUID REFERENCES auth.users(id);
ALTER TABLE public.emergencies ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE public.emergencies ENABLE ROW LEVEL SECURITY;

-- Anyone logged in can see active/accepted emergencies --
CREATE POLICY "Authenticated users can see emergencies" ON public.emergencies
    FOR SELECT TO authenticated USING (true);

-- Users can only create emergencies as themselves --
CREATE POLICY "Users can create own emergencies" ON public.emergencies
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

-- Only the owner OR the assigned helper can update an emergency status --
CREATE POLICY "Owner or helper can update emergency status" ON public.emergencies
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id OR auth.uid() = helper_id);

-- 4. Simple Rate Limiting (Preventing SOS Spam) --
-- Limit: 3 SOS per 5 minutes per user --
CREATE OR REPLACE FUNCTION check_sos_limit()
RETURNS TRIGGER AS $$
BEGIN
    IF (
        SELECT COUNT(*)
        FROM public.emergencies
        WHERE user_id = auth.uid()
        AND created_at > (now() - INTERVAL '5 minutes')
    ) >= 3 THEN
        RAISE EXCEPTION 'Too many SOS requests. Please wait a few minutes.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to enforce rate limit on emergencies --
DROP TRIGGER IF EXISTS tr_limit_sos ON public.emergencies;
CREATE TRIGGER tr_limit_sos
    BEFORE INSERT ON public.emergencies
    FOR EACH ROW
    EXECUTE FUNCTION check_sos_limit();

-- 5. Suspicious Activity Log (Audit) --
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS reports_count INTEGER DEFAULT 0;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_blacklisted BOOLEAN DEFAULT false;

-- DONE! --
