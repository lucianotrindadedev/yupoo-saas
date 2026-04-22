import sqlite3, os

DB_PATH = os.getenv("DB_PATH", "/data/yupoo.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Banco não encontrado em {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN job_type TEXT DEFAULT 'album'")
        conn.commit()
        print("Coluna job_type adicionada com sucesso!")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Coluna job_type já existe.")
        else:
            print(f"Erro na migração: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
