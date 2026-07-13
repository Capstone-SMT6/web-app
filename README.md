---
title: SmaCoFit Backend API (FastAPI)
emoji: 🏋️
colorFrom: green
colorTo: blue
sdk: docker
pinned: false
---

# SmaCoFit Backend API (FastAPI)

SmaCoFit adalah solusi **Smart Coach Fitness** inovatif yang menggunakan kecerdasan buatan untuk bertindak sebagai *Personal Trainer* 24/7. Repositori `web-app` ini adalah inti dari seluruh kecerdasan tersebut.

Layanan backend berbasis Python (FastAPI) ini menangani fungsi-fungsi krusial berikut:
- **LLM Integration (Gemini/OpenAI)**: Bertanggung jawab mengevaluasi performa *workout* pengguna, menyusun jadwal pelatihan harian, dan menganalisis asupan nutrisi secara dinamis.
- **RAG Chatbot Engine**: Chatbot kebugaran dengan teknologi *Retrieval-Augmented Generation* (menggunakan ChromaDB & Gemini) yang memungkinkan LLM membaca konteks riwayat olahraga dan kalori pengguna, sehingga konsultasi terasa sangat personal.
- **Data Persistence**: Pengoperasian database PostgreSQL (melalui SQLModel/Alembic) untuk menyimpan profil klien, log latihan (Reps/Duration), dan kalender diet pengguna.
- **Authentication**: Pengelolaan sesi pengguna menggunakan JWT yang diintegrasikan dengan Firebase/SSO dari sisi Mobile App.

---

## 🛠️ Prerequisites
- Python 3.10+
- PostgreSQL database (installed and running locally)

## 🚀 Setup Instructions

1. **Create Virtual Environment**
   Disarankan untuk memisahkan *dependencies*. Buat dan aktifkan *virtual environment*:
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Dependencies**
   Instal FastAPI, SQLModel, Alembic, dan *library* LLM lainnya:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**
   Kredensial sensitif tidak akan pernah di-*push* ke repositori ini.
   - *Copy* file *template*: `cp .env.example .env`
   - Buka `.env`, masukkan *password* PostgreSQL kamu ke dalam `DATABASE_URL`, dan tambahkan `SECRET_KEY` serta `GEMINI_API_KEY`.
   - **Catatan:** Backend akan *crash* dan menolak menyala jika `SECRET_KEY` atau `GEMINI_API_KEY` tidak disetel!

4. **Run Database Migrations (Alembic)**
   Terapkan skema model SmaCoFit ke dalam PostgreSQL:
   ```bash
   alembic upgrade head
   ```
   *Jika kamu baru saja mengubah arsitektur database di `models.py`:*
   ```bash
   alembic revision --autogenerate -m "describe_your_change"
   alembic upgrade head
   ```

5. **Setup GenAI & Knowledge Base**
   Pastikan `.env` memiliki `GEMINI_API_KEY`. Jalankan skrip ini untuk mengisi (populasi) *vector store* ChromaDB agar AI Chatbot memiliki pengetahuan dasar seputar SmaCoFit:
   ```bash
   python ingest.py
   ```

6. **Run the Server**
   Jalankan server FastAPI:
   ```bash
   fastapi dev main.py
   ```
   *(Atau bisa juga dengan `uvicorn main:app --reload`)*

   Setelah berjalan, API *endpoints* SmaCoFit dapat diakses pada `http://127.0.0.1:8000`.
   Untuk mengecek ketersediaan rute (API Docs interaktif), silakan buka `http://127.0.0.1:8000/docs`.
