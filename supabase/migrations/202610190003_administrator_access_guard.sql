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
commit;
