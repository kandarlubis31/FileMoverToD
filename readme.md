# MoveMate

MoveMate adalah aplikasi desktop berbasis Python untuk memindahkan folder antar drive dengan aman dan otomatis membuat symbolic links (symlinks). Tool ini sangat berguna untuk mengosongkan ruang di drive sistem (C:) tanpa merusak path instalasi aplikasi atau game.

## Fitur Utama

- **Robocopy Integration**: Pemindahan file antar drive yang stabil dan cepat menggunakan engine Robocopy bawaan Windows.
- **Real-time Progress**: Pantau persentase, kecepatan transfer, dan estimasi waktu selesai secara langsung.
- **Automatic Symlink**: Otomatis membuat shortcut sistem (symbolic link) di lokasi asal setelah folder berhasil dipindahkan.
- **Restore & Undo**: Mengembalikan folder ke lokasi asli dan menghapus symlink secara otomatis.
- **Queue Management**: Tambahkan beberapa folder sekaligus ke dalam antrean sebelum mulai proses pemindahan.
- **History Tracking**: Mencatat semua riwayat pemindahan folder agar mudah dilacak.

## Prasyarat

Aplikasi ini butuh Python 3.x dan library tambahan:

pip install ttkbootstrap

## Cara Penggunaan

### Memindahkan Folder
1. Jalankan aplikasi dengan hak akses Administrator.
2. Tentukan **Default Destination** (folder tujuan utama, arahkan ke D:\Games atau path spesifik lainnya).
3. Pilih folder yang mau dipindahkan di bagian **Add Source Folder**.
4. Klik **Add to Queue**.
5. Setelah semua folder masuk antrean, klik **Start**.

### Mengembalikan Folder (Via Aplikasi)
1. Buka tab **Restore**.
2. Pilih riwayat pemindahan yang ingin dikembalikan dari daftar.
3. Klik tombol **Restore Selected**.
4. Aplikasi akan otomatis menghapus symlink di lokasi awal dan memindahkan folder kembali dari tujuan ke asalnya.

### Mengembalikan Folder (Manual tanpa Aplikasi)
Jika lu perlu mengembalikan posisi folder secara manual melalui File Explorer Windows:
1. Buka lokasi folder awal tempat symlink berada.
2. Klik kanan pada folder symlink tersebut dan pilih **Delete** (Hanya menghapus shortcut, data asli tetap aman di drive tujuan).
3. Buka lokasi drive tujuan tempat data asli disimpan.
4. Cut folder tersebut, lalu Paste kembali ke lokasi awal tadi.

## Catatan Penting

- **Hak Akses Admin**: Tanpa akses Administrator, aplikasi tetap bisa memindahkan folder tapi fitur pembuatan symbolic link tidak akan berfungsi.
- **Keamanan Data**: MoveMate menggunakan Robocopy dengan verifikasi data. Proses pemindahan dijamin tidak merusak struktur file asli.

## Struktur File

- `movemate.py`: Script utama aplikasi.
- `movemate_history.json`: Menyimpan data riwayat transfer.
- `filemover_settings.json`: Menyimpan preferensi lokasi folder dan ukuran jendela.

---

## English

**MoveMate** is a desktop Python application that moves folders between drives with Robocopy and then creates a symbolic link at the original path, so installed applications and games keep working while the system drive is freed.

It supports real-time progress, a transfer queue, restore and undo (including manual restore), and a history of every move.
