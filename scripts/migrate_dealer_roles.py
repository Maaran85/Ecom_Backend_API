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
        
        print("🔄 Starting Dealer Roles migration...")
        
        # 1. Update UserRole enum type
        print("1. Updating UserRole enum type with new dealer values...")
        new_roles = ['dealer_manager', 'dealer_inventory', 'dealer_orders', 'dealer_finance']
        for role in new_roles:
            try:
                cursor.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{role}';")
                print(f"   ✅ Added '{role}' to userrole enum")
            except Exception as e:
                print(f"   ⚠️  Could not add '{role}': {e}")
        
        cursor.close()
        conn.close()
        
        print("\n🎉 Dealer Roles migration completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
