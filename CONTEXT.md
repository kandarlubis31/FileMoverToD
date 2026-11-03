# FileMoverToD — Project Context

## Ringkasan

MoveMate: utilitas desktop Windows untuk memindahkan folder dari drive sistem ke drive lain, lalu
menggantinya dengan symbolic link. Path asli tetap valid, jadi aplikasi atau game yang memakainya
tidak sadar foldernya sudah pindah.

## Arsitektur

Satu berkas GUI (`movemate.py`) dengan ttkbootstrap. Pemindahan diserahkan ke **Robocopy** bawaan
Windows, bukan `shutil`, karena Robocopy punya resume, retry, dan pelaporan progres yang sudah
teruji. Proses dijalankan sebagai subprocess dan output-nya diurai untuk mengisi bilah progres.

Setelah salinan terverifikasi, folder asal dihapus dan diganti symlink
(`mklink /D`). Operasi dicatat di `filemover_settings.json` agar bisa dibatalkan: undo menghapus
symlink dan memindahkan isi folder kembali.

Antrean memungkinkan beberapa folder dimasukkan sekaligus; masing-masing dikerjakan berurutan
supaya beban disk tidak bertumpuk.

## Struktur

```
movemate.py               Aplikasi lengkap: UI, antrean, Robocopy, symlink, undo, riwayat
filemover_settings.json   Riwayat pemindahan dan preferensi
folder_mover_pro.spec     Konfigurasi PyInstaller (nama lama, sebelum jadi MoveMate)
readme.md                 Dokumentasi pengguna
```

## Menjalankan

```bash
pip install ttkbootstrap
python movemate.py
```

Build installer/exe:

```bash
pyinstaller folder_mover_pro.spec
```

## Catatan penting

- Symlink di Windows butuh hak Administrator atau Developer Mode aktif.
- Memindahkan folder aplikasi yang **sedang berjalan** akan gagal; tutup aplikasinya dulu.
- Jangan jalankan undo pada folder yang sudah berubah isinya di lokasi baru.
