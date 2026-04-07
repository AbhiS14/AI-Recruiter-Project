import sqlite3

# Connect to your existing database
conn = sqlite3.connect('database.db')
cur = conn.cursor()

# Add the new column "score" to the resumes table
try:
    cur.execute("ALTER TABLE resumes ADD COLUMN score INTEGER")
    print("✅ 'score' column added successfully.")
except sqlite3.OperationalError:
    print("⚠️ 'score' column already exists.")

# Save and close
conn.commit()
conn.close()
