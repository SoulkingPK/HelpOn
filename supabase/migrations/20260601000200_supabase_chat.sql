-- HelpOn Real-Time Chat Migration --
-- Run this in your Supabase SQL Editor (https://supabase.com/dashboard/project/_/sql/new) --

-- Create Messages Table
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sender_id UUID REFERENCES public.profiles(id) NOT NULL,
    recipient_id UUID REFERENCES public.profiles(id) NOT NULL,
    emergency_id UUID REFERENCES public.emergencies(id), -- Optional connection to active incident
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable Row-Level Security
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

-- Select Policy: Users can only read messages sent by them or to them
CREATE POLICY "Users can select own messages" ON public.messages
    FOR SELECT TO authenticated
    USING (auth.uid() = sender_id OR auth.uid() = recipient_id);

-- Insert Policy: Users can only send messages as themselves
CREATE POLICY "Users can insert own messages" ON public.messages
    FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = sender_id);

-- Enable Realtime Publication for Messages
-- This allows clients to listen to inserts/updates using Supabase JS client libraries
ALTER PUBLICATION supabase_realtime ADD TABLE public.messages;
