import sqlite3

# Connect to your SQLite database
conn = sqlite3.connect('database.db')
cur = conn.cursor()

# Try to add the new column 'cultural_score'
try:
    cur.execute("ALTER TABLE resumes ADD COLUMN cultural_score INTEGER")
    print("✅ 'cultural_score' column added successfully.")
except sqlite3.OperationalError:
    print("⚠️ Column 'cultural_score' already exists.")

conn.commit()
conn.close()
