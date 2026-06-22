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
        
        print("Starting Partner Roles migration...")
        
        # 1. Update UserRole enum type
        print("1. Updating UserRole enum type with new partner values...")
        new_roles = [
            'partner_logistics_specialist',
            'partner_finance_specialist',
            'partner_catalog_manager',
            'partner_tech_support',
            'partner_support_manager'
        ]
        for role in new_roles:
            try:
                cursor.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{role}';")
                print(f"   Added '{role}' to userrole enum")
            except Exception as e:
                print(f"   Could not add '{role}': {e}")
        
        cursor.close()
        conn.close()
        
        print("\nPartner Roles migration completed successfully!")
        
    except Exception as e:
        print(f"\nMigration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
