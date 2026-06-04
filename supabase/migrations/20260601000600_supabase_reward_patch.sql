-- ============================================================
-- HelpOn Reward Redemption Security Patch
-- Run in: https://supabase.com/dashboard/project/yatmmbytwhpngzofiukt/sql/new
-- ============================================================

-- 1. SECURE DATABASE REDEMPTION FUNCTION
-- Handles point validation, decrement, and redemption insertion in a single transaction.
-- Locks the profiles row for update to prevent concurrent race conditions.
CREATE OR REPLACE FUNCTION public.redeem_reward_secure(
    p_user_id UUID,
    p_reward_id VARCHAR(50),
    p_voucher_code VARCHAR(255)
)
RETURNS JSON AS $$
DECLARE
    v_points_cost INTEGER;
    v_user_points INTEGER;
    v_new_points INTEGER;
BEGIN
    -- Get the reward points cost
    SELECT points_cost INTO v_points_cost
    FROM public.rewards
    WHERE id = p_reward_id;

    IF v_points_cost IS NULL THEN
        RETURN json_build_object('success', false, 'error', 'Reward or donation project not found.');
    END IF;

    -- Get user current points, locking the row to prevent concurrent race conditions
    SELECT points INTO v_user_points
    FROM public.profiles
    WHERE id = p_user_id
    FOR UPDATE;

    IF v_user_points IS NULL THEN
        RETURN json_build_object('success', false, 'error', 'User profile not found.');
    END IF;

    IF v_user_points < v_points_cost THEN
        RETURN json_build_object('success', false, 'error', 'Insufficient points.');
    END IF;

    v_new_points := v_user_points - v_points_cost;

    -- Deduct points (this decreases points, so the restrict_profile_updates trigger allows it)
    UPDATE public.profiles
    SET points = v_new_points
    WHERE id = p_user_id;

    -- Create redemption record
    INSERT INTO public.redemptions (user_id, reward_id, voucher_code)
    VALUES (p_user_id, p_reward_id, p_voucher_code);

    RETURN json_build_object(
        'success', true,
        'voucher_code', p_voucher_code,
        'new_balance', v_new_points
    );
END;
-- SECURITY DEFINER runs as the function owner (postgres), not the calling role.
-- SET search_path prevents search_path hijacking: without this, a rogue schema
-- earlier in the search_path could shadow public.profiles or public.rewards.
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog;

-- Grant execution permission to authenticated users (so the edge function running with auth context, or service_role, can call it)
GRANT EXECUTE ON FUNCTION public.redeem_reward_secure(UUID, VARCHAR, VARCHAR) TO authenticated;
GRANT EXECUTE ON FUNCTION public.redeem_reward_secure(UUID, VARCHAR, VARCHAR) TO service_role;

-- 2. HARDEN REDEMPTIONS TABLE POLICY
-- Revoke direct insert capabilities on the redemptions table from the client side.
-- This forces all redemptions to route through the Edge Function / RPC.
DROP POLICY IF EXISTS "Users can create own redemptions" ON public.redemptions;

-- User can still see their own redemptions history
DROP POLICY IF EXISTS "Users can see own redemptions" ON public.redemptions;
CREATE POLICY "Users can see own redemptions" ON public.redemptions
    FOR SELECT TO authenticated USING (auth.uid() = user_id);
