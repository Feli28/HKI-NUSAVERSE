# NusaVerse: Login, Sign Up & Email Verification

Flask + Supabase Auth. **Versi mobile**: tampilan mengikuti desain Figma (semua teks bahasa Inggris).
Di HP tampil layar penuh; di desktop tampil sebagai bingkai ukuran HP (430px).

**Layar:** Log In, Sign Up, Check Your Email, Email Verified, Forgot Password, Create New Password, Home.

**Fitur:** verifikasi email (tautan berlaku 30 menit), Resend Verification (jeda 60 detik), Forgot / Reset Password,
Log Out, username unik tidak peka huruf besar/kecil, rate limiting, CSRF, sesi aman.

**Khusus mobile:** target sentuh 48px, input 16px (mencegah zoom otomatis di iOS), dukungan notch / safe-area,
keyboard yang sesuai (`inputmode`, `enterkeyhint`), dan bisa di-*Add to Home Screen* (manifest + ikon) sehingga
tampil seperti aplikasi.

```
nusaverse/
├─ run.py
├─ requirements.txt
├─ .env.example
├─ supabase/
│  ├─ schema.sql                      <- jalankan di Supabase SQL Editor
│  └─ email-templates/
│     ├─ confirm-signup.html          <- tempel di template "Confirm sign up"
│     └─ reset-password.html          <- tempel di template "Reset password"
└─ app/
   ├─ __init__.py                     <- app factory, muat user per request
   ├─ config.py  extensions.py  security.py  supabase_client.py
   ├─ services/profiles.py            <- query tabel profiles + operasi admin Auth
   ├─ blueprints/auth.py              <- login, signup, check-email, confirm, forgot/reset, logout
   ├─ blueprints/main.py              <- halaman home (tempat UI klasifikasi nanti)
   ├─ templates/                      <- login, signup, check_email, forgot_password, reset_password, message, home, error
   └─ static/css/style.css, img/ (logo, ikon PWA)
```

---

## 1. Buat project Supabase

1. Buat project baru di https://supabase.com. Pilih region **Singapore** (paling dekat dengan Indonesia).
2. Buka **SQL Editor > New query**, tempel isi `supabase/schema.sql`, lalu **Run**.
   Ini membuat tabel `profiles`, trigger yang otomatis membuat profil untuk setiap akun baru, dan fungsi cek username.

## 2. Pengaturan Auth di dashboard Supabase

| Menu | Yang diatur |
|---|---|
| **Authentication > URL Configuration** | **Site URL** = `http://127.0.0.1:5000` (saat deploy ganti ke URL produksi) |
| **Authentication > Sign In / Providers > Email** | **Confirm email** = ON, **Minimum password length** = 8, **Email OTP Expiration** = `1800` (detik = 30 menit, supaya sesuai teks "valid for 30 minutes") |
| **Authentication > Emails > SMTP Settings** | Aktifkan **Custom SMTP** (lihat bagian 3, ini wajib) |
| **Authentication > Emails > Templates** | Isi **Confirm sign up** dan **Reset password** (lihat bagian 4) |

> **Penting:** buka aplikasi lewat alamat yang **sama persis** dengan Site URL (`127.0.0.1`, jangan `localhost`),
> karena tautan di email akan mengarah ke Site URL.

## 3. SMTP sendiri (wajib)

Email bawaan Supabase hanya untuk uji coba: **hanya terkirim ke anggota tim project** dan jumlahnya sangat dibatasi,
jadi pengguna publik tidak akan menerima email verifikasi. Template email juga tidak bisa diedit tanpa SMTP sendiri.

Pilih salah satu penyedia (semua punya paket gratis/murah): **Brevo**, **Resend**, **SendGrid**, **AWS SES**,
atau **Gmail** (pakai App Password, cukup untuk uji coba, batasnya ~500 email/hari).
Isi di **Authentication > Emails > SMTP Settings**: host, port, username, password/SMTP key, dan sender email
(alamat pengirim harus sudah diverifikasi di penyedia). Setelah SMTP sendiri aktif, batas kirim email naik
(bawaan 30 email/jam, bisa diubah di pengaturan rate limit).

## 4. Template email

Di **Authentication > Emails > Templates**:

1. **Confirm sign up**: Subject `Verify your NusaVerse email`, isi dengan `supabase/email-templates/confirm-signup.html`.
2. **Reset password**: Subject `Reset your NusaVerse password`, isi dengan `supabase/email-templates/reset-password.html`.

Tautan di template mengarah ke `{{ .SiteURL }}/auth/confirm?token_hash=...`, yang diproses oleh aplikasi ini.
Jangan pakai `{{ .ConfirmationURL }}` bawaan, karena alurnya berbeda.

## 5. API key

Dashboard: **Project Settings > API Keys**.

- `SUPABASE_URL`: Project URL
- `SUPABASE_PUBLISHABLE_KEY`: `sb_publishable_...` (key legacy: `anon`)
- `SUPABASE_SECRET_KEY`: `sb_secret_...` (key legacy: `service_role`). **Rahasia: hanya di `.env` server, jangan di-commit.**

## 6. Jalankan

```bash
python -m venv venv
venv\Scripts\activate            # Windows   (macOS/Linux: source venv/bin/activate)
python -m pip install -r requirements.txt
copy .env.example .env           # lalu isi SECRET_KEY dan key Supabase
python run.py                    # http://127.0.0.1:5000
```

Gunakan `python -m pip` (bukan `pip`) supaya paket terpasang di venv yang sedang aktif.

### Membuat akun admin
Daftar dulu lewat aplikasi dan verifikasi emailnya, lalu di SQL Editor:
```sql
update public.profiles set role = 'admin' where lower(username) = lower('namaKamu');
```

## 7. Menguji di HP

Kamera HP dan "Add to Home Screen" hanya jalan di **HTTPS**, jadi `http://192.168.x.x:5000` tidak cukup.
Cara paling mudah: pakai tunnel HTTPS, misalnya Cloudflare Tunnel atau ngrok:

```bash
python run.py                                  # terminal 1
ngrok http 5000                                # terminal 2 -> dapat https://xxxx.ngrok-free.app
```

Lalu di Supabase **Authentication > URL Configuration**, ubah **Site URL** menjadi alamat https tadi,
dan buka aplikasi dari HP lewat alamat itu. Kalau tidak, tautan di email verifikasi akan mengarah ke alamat lama.
Setelah selesai uji, kembalikan Site URL (atau isi dengan URL produksi).

## 8. Cara kerja singkat

- **Sign Up**: cek format + username tersedia -> `auth.sign_up` -> Supabase mengirim email -> halaman *Check Your Email*.
- **Klik tautan di email** -> `/auth/confirm` memverifikasi token (sekali pakai, 30 menit) -> halaman *Email Verified*.
- **Log In** hanya berhasil jika email sudah terverifikasi. Bila belum, pengguna diarahkan ke *Check Your Email* untuk kirim ulang.
- **Resend Verification**: tombol nonaktif 60 detik dengan hitung mundur; dibatasi juga di server.
- **Back to Sign Up** (salah ketik email): akun yang belum terverifikasi itu dihapus supaya username-nya bisa dipakai lagi.
- **Forgot Password**: selalu menampilkan pesan yang sama, baik email terdaftar maupun tidak (tidak membocorkan data akun).
- **Reset password** menaikkan `session_version`, sehingga semua sesi lama di perangkat lain otomatis keluar.
- Akun dengan `is_active = false` tidak bisa login dan sesinya langsung tidak berlaku.

## 9. Menyambungkan halaman klasifikasi

1. Salin `prediction.py` ke `app/blueprints/` (impor `from ..security import login_required` sudah cocok).
2. Daftarkan di `app/__init__.py` (baris contoh sudah ada, tinggal hapus tanda `#`).
3. Tempel UI klasifikasi ke `app/templates/home.html` (ada penanda di sana).
4. **CSRF aktif.** Setiap `fetch(..., {method: "POST"})` ke `/predict` harus mengirim header token:
   ```js
   const csrf = document.querySelector('meta[name="csrf-token"]').content;
   fetch("/predict", { method: "POST", body: formData, headers: { "X-CSRFToken": csrf } });
   ```
   (`base.html` sudah memuat `<meta name="csrf-token">`.)

## 10. Catatan produksi

- Set `FLASK_ENV=production` (cookie jadi `Secure`) dan `BEHIND_PROXY=1` bila di belakang reverse proxy; wajib HTTPS.
- Jalankan dengan `gunicorn "app:create_app()"`. Rate limit memakai memori proses; untuk banyak worker ganti ke Redis di `app/extensions.py`.
- Akun yang tidak pernah diverifikasi menumpuk di `auth.users`. Bersihkan berkala (manual atau `pg_cron`):
  ```sql
  delete from auth.users where email_confirmed_at is null and created_at < now() - interval '1 day';
  ```
- Aplikasi memuat profil dari Supabase di setiap request; region Singapore membuatnya cepat.

## 11. Troubleshooting

| Gejala | Penyebab umum |
|---|---|
| Sign up berhasil tapi email tidak datang | SMTP sendiri belum aktif (email bawaan hanya ke anggota tim), cek folder spam |
| "Email rate limit exceeded" | Batas kirim email Supabase; tunggu atau naikkan di Auth > Rate Limits |
| Klik tautan -> "Link Expired" | Template email belum diganti ke `/auth/confirm?...`, OTP expiry terlalu pendek, atau tautan sudah dipakai |
| Tautan email membuka alamat yang salah | **Site URL** belum sama dengan alamat aplikasi |
| Tombol Resend / link email di HP tidak jalan | Site URL masih `127.0.0.1`; pakai tunnel HTTPS (bagian 7) |
| `Invalid API key` saat start | `pip install -U supabase`, atau pakai key legacy (`anon` / `service_role`) |
| Login: "account isn't set up correctly" | `schema.sql` belum dijalankan saat akun dibuat (profil tidak ada) |
| "We couldn't create your account" | Username bentrok tepat bersamaan; coba username lain |
