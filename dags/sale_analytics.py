from airflow import DAG
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import random

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def generate_sales_data():
    """Generate mock sales data and insert into database"""
    hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # Generate 50 random sales records
    products = ['Laptop', 'Mouse', 'Keyboard', 'Monitor', 'Headphones']
    regions = ['North', 'South', 'East', 'West']
    
    insert_query = """
        INSERT INTO sales_transactions (transaction_date, product, quantity, unit_price, region)
        VALUES (%s, %s, %s, %s, %s)
    """
    
    for _ in range(50):
        transaction_date = datetime.now().date()
        product = random.choice(products)
        quantity = random.randint(1, 10)
        unit_price = random.randint(10, 500)
        region = random.choice(regions)
        
        hook.run(insert_query, parameters=(transaction_date, product, quantity, unit_price, region))
    
    print(f"Inserted 50 sales records")

def validate_data_quality():
    """Check data quality - ensure no negative values"""
    hook = PostgresHook(postgres_conn_id='postgres_default')
    
    check_query = """
        SELECT COUNT(*) as bad_records
        FROM sales_transactions
        WHERE quantity < 0 OR unit_price < 0
    """
    
    result = hook.get_first(check_query)
    bad_records = result[0]
    
    if bad_records > 0:
        raise ValueError(f"Data quality check failed! Found {bad_records} records with negative values")
    
    print("Data quality check passed!")

def print_top_products():
    """Print top 5 products by revenue"""
    hook = PostgresHook(postgres_conn_id='postgres_default')
    
    query = """
        SELECT product, total_revenue, total_quantity
        FROM daily_product_summary
        ORDER BY total_revenue DESC
        LIMIT 5
    """
    
    records = hook.get_records(query)
    
    print("\n=== TOP 5 PRODUCTS BY REVENUE ===")
    for record in records:
        print(f"Product: {record[0]}, Revenue: ${record[1]:.2f}, Quantity: {record[2]}")

with DAG(
    'sales_analytics_pipeline',
    default_args=default_args,
    description='Daily sales analytics pipeline with PostgreSQL',
    schedule_interval='@daily',
    catchup=False,
    tags=['demo', 'postgres', 'etl'],
) as dag:

    # Task 1: Create tables if they don't exist
    create_tables = PostgresOperator(
        task_id='create_tables',
        postgres_conn_id='postgres_default',
        sql="""
            -- Main transactions table
            CREATE TABLE IF NOT EXISTS sales_transactions (
                id SERIAL PRIMARY KEY,
                transaction_date DATE NOT NULL,
                product VARCHAR(100) NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(10, 2) NOT NULL,
                region VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Summary table for analytics
            CREATE TABLE IF NOT EXISTS daily_product_summary (
                id SERIAL PRIMARY KEY,
                summary_date DATE NOT NULL,
                product VARCHAR(100) NOT NULL,
                total_quantity INTEGER NOT NULL,
                total_revenue DECIMAL(12, 2) NOT NULL,
                avg_price DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(summary_date, product)
            );

            -- Regional summary table
            CREATE TABLE IF NOT EXISTS daily_regional_summary (
                id SERIAL PRIMARY KEY,
                summary_date DATE NOT NULL,
                region VARCHAR(50) NOT NULL,
                total_revenue DECIMAL(12, 2) NOT NULL,
                transaction_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(summary_date, region)
            );
        """
    )

    # Task 2: Generate mock sales data
    generate_data = PythonOperator(
        task_id='generate_sales_data',
        python_callable=generate_sales_data
    )

    # Task 3: Validate data quality
    validate_data = PythonOperator(
        task_id='validate_data_quality',
        python_callable=validate_data_quality
    )

    # Task 4: Calculate daily product summary
    calculate_product_summary = PostgresOperator(
        task_id='calculate_product_summary',
        postgres_conn_id='postgres_default',
        sql="""
            INSERT INTO daily_product_summary (summary_date, product, total_quantity, total_revenue, avg_price)
            SELECT 
                CURRENT_DATE as summary_date,
                product,
                SUM(quantity) as total_quantity,
                SUM(quantity * unit_price) as total_revenue,
                AVG(unit_price) as avg_price
            FROM sales_transactions
            WHERE transaction_date = CURRENT_DATE
            GROUP BY product
            ON CONFLICT (summary_date, product) 
            DO UPDATE SET
                total_quantity = EXCLUDED.total_quantity,
                total_revenue = EXCLUDED.total_revenue,
                avg_price = EXCLUDED.avg_price,
                created_at = CURRENT_TIMESTAMP;
        """
    )

    # Task 5: Calculate daily regional summary
    calculate_regional_summary = PostgresOperator(
        task_id='calculate_regional_summary',
        postgres_conn_id='postgres_default',
        sql="""
            INSERT INTO daily_regional_summary (summary_date, region, total_revenue, transaction_count)
            SELECT 
                CURRENT_DATE as summary_date,
                region,
                SUM(quantity * unit_price) as total_revenue,
                COUNT(*) as transaction_count
            FROM sales_transactions
            WHERE transaction_date = CURRENT_DATE
            GROUP BY region
            ON CONFLICT (summary_date, region)
            DO UPDATE SET
                total_revenue = EXCLUDED.total_revenue,
                transaction_count = EXCLUDED.transaction_count,
                created_at = CURRENT_TIMESTAMP;
        """
    )

    # Task 6: Print top products report
    print_report = PythonOperator(
        task_id='print_top_products_report',
        python_callable=print_top_products
    )

    # Task 7: Archive old data (older than 30 days)
    archive_old_data = PostgresOperator(
        task_id='archive_old_data',
        postgres_conn_id='postgres_default',
        sql="""
            DELETE FROM sales_transactions
            WHERE transaction_date < CURRENT_DATE - INTERVAL '30 days';
        """
    )

    # Define task dependencies
    create_tables >> generate_data >> validate_data
    validate_data >> [calculate_product_summary, calculate_regional_summary]
    [calculate_product_summary, calculate_regional_summary] >> print_report
    print_report >> archive_old_data