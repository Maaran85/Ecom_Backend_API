import asyncio
import asyncpg

async def main():
    print("Connecting to source database (online_seller_db)...")
    source_conn = await asyncpg.connect('postgresql://postgres:admin@localhost:5432/online_seller_db')
    
    print("Connecting to destination database (onlineshopappdb)...")
    dest_conn = await asyncpg.connect('postgresql://postgres:admin@localhost:5432/onlineshopappdb')
    
    print("Fetching pincode data from source...")
    records = await source_conn.fetch("""
        SELECT circle_name, region_name, division_name, office_name, pincode, 
               office_type, delivery_status, district, state_name, latitude, longitude, created_at
        FROM pincode_master
    """)
    print(f"Fetched {len(records)} records.")
    
    if records:
        print("Truncating existing destination table to prevent duplicates...")
        await dest_conn.execute("TRUNCATE TABLE pincode_master RESTART IDENTITY")
        
        print("Inserting records into destination...")
        tuples = [
            (
                r['circle_name'], r['region_name'], r['division_name'], r['office_name'],
                r['pincode'], r['office_type'], r['delivery_status'], r['district'],
                r['state_name'], r['latitude'], r['longitude'], r['created_at']
            ) for r in records
        ]
        
        await dest_conn.copy_records_to_table(
            'pincode_master',
            columns=['circle_name', 'region_name', 'division_name', 'office_name', 
                     'pincode', 'office_type', 'delivery_status', 'district', 
                     'state_name', 'latitude', 'longitude', 'created_at'],
            records=tuples
        )
        print("Data insertion complete.")
        
    await source_conn.close()
    await dest_conn.close()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
