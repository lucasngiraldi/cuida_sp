# create_admin.py
import argparse, bcrypt
from db import init_db, get_user_by_email, create_user

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--role", default="admin")
    args = p.parse_args()

    init_db()
    if get_user_by_email(args.email):
        print("Já existe usuário com esse e-mail.")
        return

    pwd_hash = bcrypt.hashpw(args.password.encode("utf-8"), bcrypt.gensalt())
    uid = create_user(args.name, args.email, pwd_hash, args.role, 1)
    print(f"Usuário criado com id={uid} e papel={args.role}")

if __name__ == "__main__":
    main()