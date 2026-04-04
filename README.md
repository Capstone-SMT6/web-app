# Capstone Backend API (FastAPI)

This is the Python-based backend that handles authentication, database connections, and API requests.

## 🛠️ Prerequisites
- Python 3.10+
- PostgreSQL database installed and running locally

## 🚀 Setup Instructions

1. **Create Virtual Environment**
   It is highly recommended to isolate dependencies. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Dependencies**
   Install FastAPI, Prisma, and all required packages:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**
   Sensitive credentials are never pushed to the repository.
   - Copy the template file: `cp .env.example .env`
   - Open `.env` and fill in your actual PostgreSQL password (`DATABASE_URL`) and generate a `SECRET_KEY`.
   - **Note:** The backend will not start if the `SECRET_KEY` is missing!

4. **Setup Database (Prisma)**
   Synchronize your Prisma schema with your local Postgres database and generate the Prisma Client for Python:
   ```bash
   prisma db push
   prisma generate
   ```

5. **Run the Server**
   Start the FastAPI development server:
   ```bash
   fastapi dev main.py
   ```
   *(Or alternatively, `uvicorn main:app --reload`)*

   Once running, the API will be available at `http://127.0.0.1:8000`.
   You can view the interactive auto-generated documentation at `http://127.0.0.1:8000/docs`.
