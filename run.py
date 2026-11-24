from app import create_app

app = create_app()

if __name__ == "__main__":
    # Buka lewat http://127.0.0.1:5001 (harus sama dengan "Site URL" di Supabase).
    app.run(debug=True, port=5001)
