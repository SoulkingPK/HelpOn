-- HelpOn NGO Console & Organizations Migration --
-- Run this in your Supabase SQL Editor (https://supabase.com/dashboard/project/_/sql/new) --

-- 1. Create Organizations Table
CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    invite_code VARCHAR(10) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Create Organization Members Table
CREATE TABLE IF NOT EXISTS public.organization_members (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE NOT NULL,
    profile_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    role VARCHAR(50) DEFAULT 'responder' NOT NULL, -- 'admin', 'responder'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    CONSTRAINT uniq_org_member UNIQUE (organization_id, profile_id)
);

-- 3. Enable Row-Level Security
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;

-- 4. RLS Policies for Organizations
CREATE POLICY "Users can select organizations they are a member of" ON public.organizations
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.organization_members 
            WHERE organization_members.organization_id = id 
            AND organization_members.profile_id = auth.uid()
        )
    );

CREATE POLICY "Authenticated users can create new organizations" ON public.organizations
    FOR INSERT TO authenticated
    WITH CHECK (true);

-- 5. RLS Policies for Organization Members
CREATE POLICY "Members can select cohort list" ON public.organization_members
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.organization_members AS self
            WHERE self.organization_id = organization_members.organization_id
            AND self.profile_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert themselves to join an organization" ON public.organization_members
    FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = profile_id);

CREATE POLICY "Admins can delete members from organization" ON public.organization_members
    FOR DELETE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.organization_members AS self
            WHERE self.organization_id = organization_members.organization_id
            AND self.profile_id = auth.uid()
            AND self.role = 'admin'
        )
    );

CREATE POLICY "Admins can update roles of members" ON public.organization_members
    FOR UPDATE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.organization_members AS self
            WHERE self.organization_id = organization_members.organization_id
            AND self.profile_id = auth.uid()
            AND self.role = 'admin'
        )
    );

-- 6. Enable Realtime Publications for Organizations and Members
ALTER PUBLICATION supabase_realtime ADD TABLE public.organizations;
ALTER PUBLICATION supabase_realtime ADD TABLE public.organization_members;
