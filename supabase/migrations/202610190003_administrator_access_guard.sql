-- Prevent parallel promotion and suspension requests from creating a suspended
-- administrator. Revoking the admin role and restoring access remain possible.
begin;
create function public.qe_guard_administrator_access() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if new.raw_app_meta_data->>'qe_role' = 'admin'
       and (coalesce(new.raw_app_meta_data->'qe_suspended' = 'true'::jsonb, false)
           or coalesce(new.banned_until > clock_timestamp(), false)) then
        raise exception using errcode = '23514',
            message = 'Revoke administrator access before suspending this account';
    end if;
    return new;
end;
$$;
revoke all on function public.qe_guard_administrator_access() from public, anon, authenticated;
create trigger qe_guard_administrator_access
    before insert or update of raw_app_meta_data, banned_until on auth.users
    for each row execute function public.qe_guard_administrator_access();

-- Readiness is checked before the app grants or revokes administrator access.
-- Do not expose this RPC or grant table access to browser roles.
create function public.qe_administrator_access_guard_ready() returns jsonb
language sql security definer set search_path = '' as $$
    select jsonb_build_object('ready', exists (
        select 1 from pg_catalog.pg_trigger t
        where t.tgrelid = 'auth.users'::regclass
          and t.tgname = 'qe_guard_administrator_access'
          and t.tgfoid = 'public.qe_guard_administrator_access()'::regprocedure
          and t.tgenabled in ('O', 'A') and not t.tgisinternal
    ));
$$;
revoke all on function public.qe_administrator_access_guard_ready() from public, anon, authenticated;
grant execute on function public.qe_administrator_access_guard_ready() to service_role;
notify pgrst, 'reload schema';
commit;
