import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def run_migration():
    try:
        # Connect to database
        conn = psycopg2.connect(
            host="localhost",
            user="postgres",
            password="admin",
            database="onlineshopappdb"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        print("🔄 Starting Hub Roles migration...")
        
        # 1. Update UserRole enum type
        print("1. Updating UserRole enum type with new values...")
        new_roles = ['hub_manager', 'hub_staff', 'hub_dispatcher', 'hub_returns']
        for role in new_roles:
            try:
                cursor.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{role}';")
                print(f"   ✅ Added '{role}' to userrole enum")
            except Exception as e:
                print(f"   ⚠️  Could not add '{role}': {e}")
        
        # 2. Add hub_id column to users table
        print("2. Adding hub_id column to users...")
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS hub_id INTEGER REFERENCES delivery_hubs(id) ON DELETE SET NULL;
        """)
        print("   ✅ hub_id column added to users table")
        
        cursor.close()
        conn.close()
        
        print("\n🎉 Hub Roles migration completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
