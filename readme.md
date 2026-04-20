# MoveMate 📦

MoveMate adalah aplikasi desktop berbasis Python untuk memindahkan folder antar drive dengan aman dan otomatis membuat symbolic links (symlinks). Tool ini sangat berguna buat lu yang mau mengosongkan ruang di drive sistem (C:) tanpa merusak path instalasi aplikasi atau game.

## Fitur Utama

- **Robocopy Integration**: Pemindahan file antar drive yang stabil dan cepat menggunakan engine Robocopy bawaan Windows.
- **Real-time Progress**: Pantau persentase, kecepatan transfer, dan estimasi waktu selesai secara langsung.
- **Automatic Symlink**: Otomatis membuat shortcut sistem (symbolic link) di lokasi asal setelah folder berhasil dipindahkan.
- **Restore System**: Bisa balikin folder ke lokasi aslinya dan hapus symlink cuma dengan satu klik.
- **Queue Management**: Tambahkan beberapa folder sekaligus ke dalam antrean sebelum mulai proses pemindahan.
- **History Tracking**: Mencatat semua riwayat pemindahan folder agar mudah dilacak atau dikembalikan.

## Prasyarat

Aplikasi ini butuh Python 3.x dan beberapa library tambahan:

- **ttkbootstrap**: Untuk tampilan UI yang modern.
- **Pillow**: (Opsional) Jika ingin menambahkan ikon.

Cara install library yang dibutuhin:
pip install ttkbootstrap

## Cara Penggunaan

1. Jalankan aplikasi dengan hak akses Administrator (wajib supaya bisa bikin symbolic link).
2. Tentukan **Default Destination** (folder tujuan utama, misal di drive D:).
3. Pilih folder yang mau dipindahkan di bagian **Add Source Folder**.
4. Klik **Add to Queue**.
5. Setelah semua folder masuk antrean, klik **Start**.

## Catatan Penting

- **Hak Akses Admin**: Tanpa akses Administrator, aplikasi tetap bisa memindahkan folder tapi fitur pembuatan symbolic link tidak akan berfungsi.
- **Keamanan Data**: MoveMate menggunakan Robocopy dengan verifikasi data. Jika proses terhenti di tengah jalan, lu bisa cek history untuk memastikan status folder tersebut.

## Struktur File

- `movemate.py`: Script utama aplikasi.
- `movemate_history.json`: Menyimpan data riwayat transfer (dibuat otomatis).
- `filemover_settings.json`: Menyimpan preferensi lokasi folder dan ukuran jendela (dibuat otomatis).