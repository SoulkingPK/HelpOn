-- HelpOn AI Triage & Storage Migration --
-- Run this in your Supabase SQL Editor (https://supabase.com/dashboard/project/_/sql/new) --

-- 1. Add Triage Columns to Emergencies Table
ALTER TABLE public.emergencies ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE public.emergencies ADD COLUMN IF NOT EXISTS severity VARCHAR(20) DEFAULT 'medium';
ALTER TABLE public.emergencies ADD COLUMN IF NOT EXISTS ai_analysis JSONB;

-- 2. Create Storage Bucket for Emergency Attachments
-- Inserts a record into Supabase storage.buckets table for public access
INSERT INTO storage.buckets (id, name, public)
VALUES ('emergency_attachments', 'emergency_attachments', true)
ON CONFLICT (id) DO NOTHING;

-- 3. Storage Security Policies
-- In Supabase, bucket object permissions are configured on storage.objects

-- Policy: Allow authenticated users to upload emergency images
CREATE POLICY "Allow authenticated users to upload emergency images" ON storage.objects
    FOR INSERT TO authenticated 
    WITH CHECK (bucket_id = 'emergency_attachments' AND auth.uid()::text = (storage.foldername(name))[1]);

-- Policy: Allow public read access to emergency images (needed to display on map/list)
CREATE POLICY "Allow public read access to emergency images" ON storage.objects
    FOR SELECT TO public
    USING (bucket_id = 'emergency_attachments');
