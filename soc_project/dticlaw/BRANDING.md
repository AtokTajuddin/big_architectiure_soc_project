# Savior agent, Panduan Merek

## Identitas

Savior agent adalah agent framework yang berjalan lokal untuk mendampingi model **savior_v2**
(Llama-Primus, fine-tune SOC) dalam operasi Security Operations Center. Berbasis fork OpenClaw yang
dikeraskan, namun dengan **akses terkontrol**: boleh memanggil Wazuh API & Shuffle webhook saat
dibutuhkan untuk memeriksa log dan mengambil tindakan. Fokusnya menandai mana TRUE POSITIVE, FALSE
POSITIVE, dan FALSE NEGATIVE, lalu menyajikan analisis & rekomendasi.

- Dibuat oleh Atok Tajuddin & tim researcher.
- Model pendamping: savior_v2 (Ollama, GPU).
- Prinsip: lokal, dapat diaudit, akses keamanan terkontrol.

## Tagline

Utama: Asisten cerdas yang tinggal di mesinmu.

Pendukung: riset, analisis, dan dokumen, tanpa data keluar.

## Lambang

Lambang merek adalah lobster, ditulis dengan glyph lobster pada antarmuka. Lobster dipilih karena mewakili cakar (claw) yang menggenggam tugas sampai tuntas. Gunakan satu lambang per layar, jangan diregangkan, jangan diberi bayangan berlebih.

## Warna

Palet diambil dari antarmuka web resmi.

| Peran | Hex |
|-------|-----|
| Latar utama | #0d1117 |
| Panel | #161b22 |
| Panel sekunder | #1c2333 |
| Garis batas | #2a3140 |
| Aksen utama | #ff6b4a |
| Aksen gelap | #b84a32 |
| Warna pengguna | #1f6feb |
| Status sukses | #3fb950 |
| Teks | #e6edf3 |
| Teks redup | #8b949e |

Aksen #ff6b4a dipakai untuk tindakan utama (tombol kirim, tautan unduh, sesi aktif). Latar gelap adalah default; jangan memakai tema terang.

## Tipografi

Tumpukan sans-serif sistem: ui-sans-serif, system-ui, Segoe UI, Roboto. Tidak ada font berbayar atau berbobot tebal berlebihan. Judul tebal, isi reguler, label kecil memakai teks redup.

## Suara dan nada

- Bahasa Indonesia, ringkas, langsung ke inti.
- Mulai dari informasi terpenting, hindari basa-basi.
- Sebut sumber saat menjawab pertanyaan berbasis dokumen.
- Akui ketika informasi tidak tersedia, jangan mengarang.

## Penggunaan

- Sebut produk sebagai Savior agent. Hindari menyebutnya DTIClaw/OpenClaw di antarmuka atau dokumen pengguna.
- Tampilkan status koneksi dan model aktif secara jujur.
- Tautan unduh dokumen memakai gaya aksen, bukan teks biasa.

## Yang dihindari

- Mengirim data percakapan ke layanan pihak ketiga tanpa izin.
- Klaim hasil tanpa eksekusi nyata (misalnya mengaku membuat file padahal tidak).
- Dekorasi berlebihan: garis hias, emoji bertumpuk, warna di luar palet.
