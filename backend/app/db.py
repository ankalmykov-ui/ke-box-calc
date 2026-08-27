import os
import psycopg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://boxcalc:change_me@localhost:5432/boxcalc"
)

def get_conn():
    return psycopg.connect(DATABASE_URL)
