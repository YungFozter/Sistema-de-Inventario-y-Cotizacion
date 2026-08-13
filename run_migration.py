from dotenv import load_dotenv
load_dotenv(override=True)
from models import migrar_clientes_existentes
migrar_clientes_existentes()
print("Migration completed successfully")
