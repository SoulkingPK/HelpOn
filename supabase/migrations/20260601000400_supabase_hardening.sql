-- HelpOn Supabase Hardening & Schemas Migration --
-- Run this in your Supabase SQL Editor (https://supabase.com/dashboard/project/_/sql/new) --

-- ==========================================
-- 1. Create Error Logs Table (for Telemetry)
-- ==========================================
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

-- Enable RLS for Error Logs
ALTER TABLE public.error_logs ENABLE ROW LEVEL SECURITY;

-- Policy: Only allow authenticated users to INSERT error logs
CREATE POLICY "Allow public insert to error_logs" ON public.error_logs
    FOR INSERT TO authenticated WITH CHECK (true);

-- ==========================================
-- 2. Standardize Profiles & Add Security Triggers
-- ==========================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Anyone can see basic profile info (needed for helpers count/list)
CREATE POLICY "Profiles are viewable by everyone" ON public.profiles
    FOR SELECT USING (true);

-- Users can only update their own profile details
CREATE POLICY "Users can update own profile" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- Trigger function to restrict profile updates (preventing points/KYC spoofing)
CREATE OR REPLACE FUNCTION restrict_profile_updates()
RETURNS TRIGGER AS $$
BEGIN
    -- Check if points are being increased directly by client-side calls
    IF (COALESCE(NEW.points, 0) > COALESCE(OLD.points, 0)) THEN
        RAISE EXCEPTION 'Direct points increment is not allowed. Points can only be earned by resolving emergencies.';
    END IF;

    -- Check if KYC status or verification flag is modified
    IF (NEW.kyc_status IS DISTINCT FROM OLD.kyc_status OR NEW.verified IS DISTINCT FROM OLD.verified) THEN
        RAISE EXCEPTION 'Direct modification of KYC or verification status is restricted.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Bind trigger to profiles table
DROP TRIGGER IF EXISTS tr_restrict_profile_fields ON public.profiles;
CREATE TRIGGER tr_restrict_profile_fields
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW
    EXECUTE FUNCTION restrict_profile_updates();

-- ==========================================
-- 3. Hardening Emergencies Table & Auto-Points
-- ==========================================
ALTER TABLE public.emergencies ADD COLUMN IF NOT EXISTS helper_id UUID REFERENCES auth.users(id);
ALTER TABLE public.emergencies ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE public.emergencies ENABLE ROW LEVEL SECURITY;

-- Anyone logged in can see active/accepted emergencies
CREATE POLICY "Authenticated users can see emergencies" ON public.emergencies
    FOR SELECT TO authenticated USING (true);

-- Users can only create emergencies as themselves
CREATE POLICY "Users can create own emergencies" ON public.emergencies
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

-- Only the owner OR the assigned helper can update an emergency status
CREATE POLICY "Owner or helper can update emergency status" ON public.emergencies
    FOR UPDATE TO authenticated
    USING (auth.uid() = user_id OR auth.uid() = helper_id);

-- Trigger function to securely award points database-side upon emergency resolution
CREATE OR REPLACE FUNCTION award_points_on_resolve()
RETURNS TRIGGER AS $$
BEGIN
    -- Award points only when transition is to 'resolved' and helper is assigned
    IF (NEW.status = 'resolved' AND (OLD.status IS DISTINCT FROM 'resolved') AND NEW.helper_id IS NOT NULL) THEN
        UPDATE public.profiles
        SET points = COALESCE(points, 0) + 20,
            helps_given = COALESCE(helps_given, 0) + 1
        WHERE id = NEW.helper_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Bind trigger to emergencies table
DROP TRIGGER IF EXISTS tr_award_points_on_resolve ON public.emergencies;
CREATE TRIGGER tr_award_points_on_resolve
    AFTER UPDATE ON public.emergencies
    FOR EACH ROW
    EXECUTE FUNCTION award_points_on_resolve();

-- ==========================================
-- 4. Simple Rate Limiting (Preventing SOS Spam)
-- ==========================================
-- Limit: 3 SOS per 5 minutes per user
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

-- Trigger to enforce rate limit on emergencies
DROP TRIGGER IF EXISTS tr_limit_sos ON public.emergencies;
CREATE TRIGGER tr_limit_sos
    BEFORE INSERT ON public.emergencies
    FOR EACH ROW
    EXECUTE FUNCTION check_sos_limit();

-- ==========================================
-- 5. Suspicious Activity Log (Audit)
-- ==========================================
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS reports_count INTEGER DEFAULT 0;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_blacklisted BOOLEAN DEFAULT false;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS helps_given INTEGER DEFAULT 0;

-- ==========================================
-- 6. Support Tickets Table
-- ==========================================
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

CREATE POLICY "Admins or users can view support tickets" ON public.support_tickets
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

-- ==========================================
-- 7. Rewards Table & Seed Data
-- ==========================================
CREATE TABLE IF NOT EXISTS public.rewards (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    points_cost INTEGER NOT NULL,
    image_color VARCHAR(100) DEFAULT 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    image_text VARCHAR(10) DEFAULT 'VCH'
);

ALTER TABLE public.rewards ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Rewards are viewable by everyone" ON public.rewards
    FOR SELECT TO authenticated USING (true);

-- Seed rewards data
INSERT INTO public.rewards (id, name, description, points_cost, image_color, image_text)
VALUES 
  ('amazon_500', '₹500 Amazon Voucher', 'Get ₹500 off on Amazon shopping India.', 1000, 'linear-gradient(135deg, #ff9900 0%, #ff5500 100%)', 'AMZN'),
  ('zomato_300', '₹300 Zomato Credit', 'Order delicious food with ₹300 off on Zomato.', 600, 'linear-gradient(135deg, #cb202d 0%, #a30000 100%)', 'ZOM'),
  ('flipkart_200', '₹200 Flipkart Voucher', 'Redeem ₹200 discount at Flipkart checkout.', 400, 'linear-gradient(135deg, #2874f0 0%, #004ba0 100%)', 'FLP'),
  ('paytm_100', '₹100 Paytm Cash', 'Get ₹100 direct cashback in Paytm Wallet.', 200, 'linear-gradient(135deg, #00baf2 0%, #005691 100%)', 'PTM'),
  ('children_foundation', 'Help Children Foundation', 'Education for underprivileged kids', 500, 'linear-gradient(135deg, #34d399 0%, #059669 100%)', 'CHILD'),
  ('elder_care', 'Elder Care Initiative', 'Supporting senior citizens', 500, 'linear-gradient(135deg, #60a5fa 0%, #2563eb 100%)', 'ELDER'),
  ('disaster_relief', 'Disaster Relief Fund', 'Emergency response and recovery', 750, 'linear-gradient(135deg, #f87171 0%, #dc2626 100%)', 'RELIEF'),
  ('animal_welfare', 'Animal Welfare Society', 'Protecting and caring for animals', 300, 'linear-gradient(135deg, #fbbf24 0%, #d97706 100%)', 'ANML')
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  points_cost = EXCLUDED.points_cost,
  image_color = EXCLUDED.image_color,
  image_text = EXCLUDED.image_text;

-- ==========================================
-- 8. Redemptions Table
-- ==========================================
CREATE TABLE IF NOT EXISTS public.redemptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    reward_id VARCHAR(50) REFERENCES public.rewards(id) NOT NULL,
    voucher_code VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.redemptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can create own redemptions" ON public.redemptions
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can see own redemptions" ON public.redemptions
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

-- ==========================================
-- 9. KYC Submissions Table
-- ==========================================
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

-- ==========================================
-- 10. Automatically Create User Profile on Signup
-- ==========================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, points, helps_given)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email),
        0,
        0
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Bind trigger to auth.users insert
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
