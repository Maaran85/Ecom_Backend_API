import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def run_migration():
    try:
        conn = psycopg2.connect(
            host="localhost",
            user="postgres",
            password="admin",
            database="onlineshopappdb"
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        new_roles = [
            'PARTNER_LOGISTICS_SPECIALIST',
            'PARTNER_FINANCE_SPECIALIST',
            'PARTNER_CATALOG_MANAGER',
            'PARTNER_TECH_SUPPORT',
            'PARTNER_SUPPORT_MANAGER'
        ]
        for role in new_roles:
            try:
                cursor.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{role}';")
                print(f"Added '{role}' to userrole enum")
            except Exception as e:
                print(f"Could not add '{role}': {e}")
        
        cursor.close()
        conn.close()
        print("Completed uppercase migration!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
