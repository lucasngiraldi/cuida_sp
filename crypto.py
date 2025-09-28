from cryptography.fernet import Fernet
import streamlit as st

def _fernet():
    return Fernet(st.secrets["app"]["fernet_key"])

def encrypt_text(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode("utf-8"))

def decrypt_text(cipher_bytes: bytes) -> str:
    return _fernet().decrypt(cipher_bytes).decode("utf-8")