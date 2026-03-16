import sqlite3
from params import *
import pandas as pd

conn = sqlite3.connect(DB_PATH)
try:
	for i in range(35, 36):
		df = pd.read_sql_query(f"SELECT * FROM samples WHERE run_id={i};", conn)
		print(df.head())
		df.to_csv(f"samples{i}.csv")
		print(f"saved samples{i}.csv successfully!")
finally:
	conn.close()

df.to_csv("samples.csv")
