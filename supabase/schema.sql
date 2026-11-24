-- =====================================================================
-- NusaVerse: skema database (Supabase / PostgreSQL)
-- Jalankan di Supabase Dashboard > SQL Editor > New query > Run
--
-- Email + password + verifikasi email ditangani oleh Supabase Auth (auth.users).
-- Tabel di bawah menyimpan data profil aplikasi.
-- =====================================================================

create table if not exists public.profiles (
  id              uuid primary key references auth.users (id) on delete cascade,
  username        text not null,
  role            text not null default 'user' check (role in ('user', 'admin')),
  is_active       boolean not null default true,
  session_version integer not null default 0,   -- dinaikkan saat password direset, agar sesi lama mati
  created_at      timestamptz not null default now(),
  last_login_at   timestamptz,
  constraint profiles_username_format check (username ~ '^[A-Za-z0-9_.]{3,30}$')
);

-- Username unik dan TIDAK peka huruf besar/kecil ("Rina" dan "rina" dianggap sama).
create unique index if not exists profiles_username_lower_key
  on public.profiles (lower(username));

-- Profil dibuat otomatis setiap ada akun baru di auth.users.
-- Role SELALU 'user'. Metadata dari klien tidak pernah dipakai untuk role.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_username text := new.raw_user_meta_data ->> 'username';
begin
  if v_username is null or v_username !~ '^[A-Za-z0-9_.]{3,30}$' then
    v_username := 'user_' || substr(replace(new.id::text, '-', ''), 1, 10);
  end if;

  insert into public.profiles (id, username) values (new.id, v_username);
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Cek ketersediaan username (tidak peka huruf besar/kecil).
create or replace function public.username_available(p_username text)
returns boolean
language sql
stable
set search_path = ''
as $$
  select not exists (
    select 1 from public.profiles where lower(username) = lower(p_username)
  );
$$;

-- ---------------------------------------------------------------------
-- KEAMANAN
-- Server Flask memakai secret key (role service_role, melewati RLS).
-- RLS diaktifkan tanpa policy + hak anon/authenticated dicabut, sehingga
-- publishable key yang bersifat publik tidak bisa membaca/menulis tabel ini.
-- ---------------------------------------------------------------------
alter table public.profiles enable row level security;

revoke all on public.profiles from anon, authenticated;

revoke all on function public.handle_new_user()          from public, anon, authenticated;
revoke all on function public.username_available(text)   from public, anon, authenticated;
grant execute on function public.username_available(text) to service_role;
