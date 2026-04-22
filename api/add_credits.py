import sqlite3, os

# O caminho no container é /data/yupoo.db
DB_PATH = os.getenv("DB_PATH", "/data/yupoo.db")

def add_credits(email, amount):
    if not os.path.exists(DB_PATH):
        print(f"Erro: Banco de dados não encontrado em {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    try:
        # Verifica se o usuário existe
        user = conn.execute("SELECT id, credits FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            print(f"Erro: Usuário {email} não encontrado no banco.")
            return
        
        new_credits = user[1] + amount
        conn.execute("UPDATE users SET credits = ? WHERE email = ?", (new_credits, email))
        conn.commit()
        print(f"Sucesso! {amount} créditos adicionados para {email}. Saldo atual: {new_credits}")
    except Exception as e:
        print(f"Erro ao atualizar: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_credits("olucianotrindade@gmail.com", 50)
