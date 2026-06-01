-- ============================================================
-- HelpOn Security Patch Migration
-- Run in: https://supabase.com/dashboard/project/yatmmbytwhpngzofiukt/sql/new
-- ============================================================

-- ============================================================
-- 0. CREATE MISSING TABLES IF THEY DO NOT EXIST
-- ============================================================
CREATE TABLE IF NOT EXISTS public.support_tickets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'open' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.support_tickets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can insert own support tickets" ON public.support_tickets
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id OR user_id IS NULL);

CREATE TABLE IF NOT EXISTS public.kyc_submissions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    document_type VARCHAR(100) NOT NULL,
    document_number VARCHAR(100) NOT NULL,
    document_image_url TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' NOT NULL,
    admin_feedback TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.kyc_submissions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can insert own KYC submissions" ON public.kyc_submissions
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can see own KYC submissions" ON public.kyc_submissions
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

CREATE TABLE IF NOT EXISTS public.messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sender_id UUID REFERENCES public.profiles(id) NOT NULL,
    recipient_id UUID REFERENCES public.profiles(id) NOT NULL,
    emergency_id UUID REFERENCES public.emergencies(id),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can select own messages" ON public.messages;
CREATE POLICY "Users can select own messages" ON public.messages
    FOR SELECT TO authenticated USING (auth.uid() = sender_id OR auth.uid() = recipient_id);

DROP POLICY IF EXISTS "Users can insert own messages" ON public.messages;
CREATE POLICY "Users can insert own messages" ON public.messages
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = sender_id);

-- Safely add messages to realtime publication if not already present
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.messages;
    END IF;
EXCEPTION
    WHEN others THEN NULL; -- Ignore errors if already added
END $$;

CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    invite_code VARCHAR(8) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone authenticated can view organizations" ON public.organizations;
CREATE POLICY "Anyone authenticated can view organizations" ON public.organizations
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Anyone authenticated can insert organizations" ON public.organizations;
CREATE POLICY "Anyone authenticated can insert organizations" ON public.organizations
    FOR INSERT TO authenticated WITH CHECK (true);

CREATE TABLE IF NOT EXISTS public.organization_members (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE NOT NULL,
    profile_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    role VARCHAR(50) DEFAULT 'responder' CHECK (role IN ('admin', 'responder')) NOT NULL,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(organization_id, profile_id)
);

ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Members can view organization roster" ON public.organization_members;
CREATE POLICY "Members can view organization roster" ON public.organization_members
    FOR SELECT TO authenticated USING (
        EXISTS (
            SELECT 1 FROM public.organization_members
            WHERE organization_id = organization_members.organization_id
            AND profile_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "Anyone authenticated can join organization" ON public.organization_members;
CREATE POLICY "Anyone authenticated can join organization" ON public.organization_members
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = profile_id);

-- ============================================================
-- 1. ADD MISSING COLUMNS TO PROFILES
-- ============================================================
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT false;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS last_active TIMESTAMP WITH TIME ZONE;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS kyc_status VARCHAR(50) DEFAULT 'unverified';
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT false;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS helps_given INTEGER DEFAULT 0;

-- ============================================================
-- 2. FIX SUPPORT TICKETS RLS POLICIES
-- (Old policy was user-scoped only — admins couldn't see all tickets)
-- ============================================================
DROP POLICY IF EXISTS "Admins or users can view support tickets" ON public.support_tickets;
DROP POLICY IF EXISTS "Users can view own support tickets" ON public.support_tickets;

-- Users see their own tickets; admins see all
CREATE POLICY "Tickets viewable by owner or admin" ON public.support_tickets
    FOR SELECT TO authenticated
    USING (
        auth.uid() = user_id
        OR EXISTS (
            SELECT 1 FROM public.profiles
            WHERE id = auth.uid() AND is_admin = true
        )
    );

-- Only admins can update ticket status (e.g., close a ticket)
DROP POLICY IF EXISTS "Only admins can update tickets" ON public.support_tickets;
CREATE POLICY "Only admins can update tickets" ON public.support_tickets
    FOR UPDATE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE id = auth.uid() AND is_admin = true
        )
    );

-- ============================================================
-- 3. FIX check_sos_limit TRIGGER
-- Use NEW.user_id instead of auth.uid() for reliability in
-- SECURITY DEFINER context
-- ============================================================
CREATE OR REPLACE FUNCTION check_sos_limit()
RETURNS TRIGGER AS $$
BEGIN
    IF (
        SELECT COUNT(*)
        FROM public.emergencies
        WHERE user_id = NEW.user_id
        AND created_at > (now() - INTERVAL '5 minutes')
    ) >= 3 THEN
        RAISE EXCEPTION 'Too many SOS requests. Please wait a few minutes.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================
-- 4. ADMIN STATS RPC FUNCTION
-- Single round-trip for all admin dashboard stats
-- ============================================================
CREATE OR REPLACE FUNCTION public.get_admin_stats()
RETURNS JSON AS $$
    SELECT json_build_object(
        'total_users',   (SELECT COUNT(*) FROM public.profiles),
        'active_sos',    (SELECT COUNT(*) FROM public.emergencies WHERE status = 'active'),
        'accepted_sos',  (SELECT COUNT(*) FROM public.emergencies WHERE status = 'accepted'),
        'resolved_sos',  (SELECT COUNT(*) FROM public.emergencies WHERE status = 'resolved'),
        'open_tickets',  (SELECT COUNT(*) FROM public.support_tickets WHERE status = 'open')
    );
$$ LANGUAGE SQL STABLE SECURITY DEFINER;

-- Allow any authenticated user to call this (admin check is done client-side after)
GRANT EXECUTE ON FUNCTION public.get_admin_stats() TO authenticated;

-- ============================================================
-- 5. PERFORMANCE INDEXES
-- All high-frequency query patterns that were missing indexes
-- ============================================================

-- emergencies table
CREATE INDEX IF NOT EXISTS idx_emergencies_status
    ON public.emergencies(status);

CREATE INDEX IF NOT EXISTS idx_emergencies_user_id
    ON public.emergencies(user_id);

CREATE INDEX IF NOT EXISTS idx_emergencies_helper_id
    ON public.emergencies(helper_id);

CREATE INDEX IF NOT EXISTS idx_emergencies_created_at
    ON public.emergencies(created_at DESC);

-- Composite index for the most common query: active/accepted emergencies ordered by date
CREATE INDEX IF NOT EXISTS idx_emergencies_status_created
    ON public.emergencies(status, created_at DESC);

-- messages table (chat history queries)
CREATE INDEX IF NOT EXISTS idx_messages_channel
    ON public.messages(sender_id, recipient_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_sent_at
    ON public.messages(created_at DESC);

-- profiles table (active user map queries)
CREATE INDEX IF NOT EXISTS idx_profiles_last_active
    ON public.profiles(last_active DESC)
    WHERE last_active IS NOT NULL;

-- organization_members (NGO membership check on every NGO page load)
CREATE INDEX IF NOT EXISTS idx_org_members_profile_id
    ON public.organization_members(profile_id);

CREATE INDEX IF NOT EXISTS idx_org_members_org_id
    ON public.organization_members(organization_id);

-- kyc_submissions (user's own KYC status check)
CREATE INDEX IF NOT EXISTS idx_kyc_user_created
    ON public.kyc_submissions(user_id, created_at DESC);

-- redemptions (reward history)
CREATE INDEX IF NOT EXISTS idx_redemptions_user_created
    ON public.redemptions(user_id, created_at DESC);

-- error_logs (telemetry queries)
CREATE INDEX IF NOT EXISTS idx_error_logs_user_created
    ON public.error_logs(user_id, created_at DESC);

-- support_tickets (admin queries)
CREATE INDEX IF NOT EXISTS idx_support_tickets_status
    ON public.support_tickets(status, created_at DESC);

-- ============================================================
-- INSTRUCTIONS AFTER RUNNING THIS MIGRATION:
-- 1. In Supabase Dashboard > Table Editor > profiles
--    Find YOUR user row and set is_admin = true
-- 2. Verify indexes were created:
--    SELECT indexname FROM pg_indexes WHERE tablename IN
--    ('emergencies','messages','profiles','organization_members',
--     'kyc_submissions','redemptions','error_logs','support_tickets');
-- ============================================================
