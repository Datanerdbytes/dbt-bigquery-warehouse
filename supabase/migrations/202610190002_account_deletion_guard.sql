-- Apply before using account deletion. The database checks the CURRENT row,
-- including changes committed after the app fetched the confirmation snapshot.
--
-- Every object is created or replaced and the trigger is dropped before it is
-- recreated, so this file can be applied again without failing.
begin;
create or replace function public.qe_guard_account_deletion() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    -- `qe_owner` and `qe_role` are compared as text, so a string "true" or
    -- "admin" still protects the account. `qe_suspended` is compared as a JSON
    -- boolean, so a malformed value fails closed and the account is not
    -- deletable rather than becoming deletable by accident.
    if old.raw_app_meta_data->>'qe_owner' = 'true'
       or old.raw_app_meta_data->>'qe_role' = 'admin'
       or not (coalesce(old.raw_app_meta_data->'qe_suspended' = 'true'::jsonb, false)
           or coalesce(old.banned_until > clock_timestamp(), false)) then
        raise exception using errcode = '23514',
            message = 'Only suspended non-administrator accounts may be deleted';
    end if;
    return old;
end;
$$;
revoke all on function public.qe_guard_account_deletion() from public, anon, authenticated;
drop trigger if exists qe_guard_account_deletion on auth.users;
create trigger qe_guard_account_deletion
    before delete on auth.users
    for each row execute function public.qe_guard_account_deletion();

-- Readiness is checked before calling Supabase's supported Admin delete API.
-- Do not expose this RPC or grant table access to browser roles.
create or replace function public.qe_account_deletion_guard_ready() returns jsonb
language sql security definer set search_path = '' as $$
    select jsonb_build_object('ready', exists (
        select 1 from pg_catalog.pg_trigger t
        where t.tgrelid = 'auth.users'::regclass
          and t.tgname = 'qe_guard_account_deletion'
          and t.tgfoid = 'public.qe_guard_account_deletion()'::regprocedure
          and t.tgenabled in ('O', 'A') and not t.tgisinternal
    ));
$$;
revoke all on function public.qe_account_deletion_guard_ready() from public, anon, authenticated;
grant execute on function public.qe_account_deletion_guard_ready() to service_role;
notify pgrst, 'reload schema';
commit;
