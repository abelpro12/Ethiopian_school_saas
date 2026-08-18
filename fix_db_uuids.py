import sqlite3

def fix_uuids():
    conn = sqlite3.connect('db.sqlite3')
    cur = conn.cursor()
    
    # Get all tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cur.fetchall()]
    
    for table in tables:
        # Get column info
        cur.execute(f"PRAGMA table_info({table});")
        columns = cur.fetchall()
        
        # In Django, uuid fields are typically named id, school_id, student_id, etc. 
        # But we can just look for columns that might contain uuids.
        # Let's just fix the 'id' column for all tables, and any column ending in '_id' if they are 36 chars.
        for col in columns:
            col_name = col[1]
            col_type = col[2].upper()
            
            # Check if there are any rows with 36-char string (UUID with hyphens)
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE length({col_name}) = 36 AND {col_name} LIKE '%-%-%-%-%'")
                count = cur.fetchone()[0]
                if count > 0:
                    print(f"Fixing {count} UUIDs in {table}.{col_name}")
                    cur.execute(f"UPDATE {table} SET {col_name} = REPLACE({col_name}, '-', '') WHERE length({col_name}) = 36 AND {col_name} LIKE '%-%-%-%-%'")
            except Exception as e:
                pass
                
    conn.commit()
    conn.close()
    print("Done fixing UUIDs!")

if __name__ == '__main__':
    fix_uuids()
