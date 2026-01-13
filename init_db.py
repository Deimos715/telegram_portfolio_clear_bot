import asyncio
from db_handler.db_funk import create_table_users

if __name__ == '__main__':
    asyncio.run(create_table_users())