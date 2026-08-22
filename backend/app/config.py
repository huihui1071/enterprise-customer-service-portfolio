import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DATA_ROOT = PROJECT_ROOT / "data"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BACKEND_ROOT / "customer_service.db"))
JWT_SECRET = os.getenv("JWT_SECRET", "portfolio-development-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
ENABLE_FAULT_INJECTION = os.getenv("ENABLE_FAULT_INJECTION", "false").lower() == "true"
APP_VERSION = "1.0.0"
