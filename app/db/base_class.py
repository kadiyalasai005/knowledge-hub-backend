# app/db/base_class.py
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData
from typing import Any
from sqlalchemy.ext.declarative import declared_attr

# Optional: Define naming conventions for indexes and constraints
# convention = {
#     "ix": "ix_%(column_0_label)s",
#     "uq": "uq_%(table_name)s_%(column_0_name)s",
#     "ck": "ck_%(table_name)s_%(constraint_name)s",
#     "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
#     "pk": "pk_%(table_name)s",
# }
# metadata = MetaData(naming_convention=convention)

class Base(DeclarativeBase):
    id: Any
    __name__: str
    # metadata = metadata # Uncomment if using naming convention

    # Generate __tablename__ automatically
    @declared_attr.directive
    def __tablename__(cls) -> str:
        # Converts class name from CamelCase to snake_case for table name
        import re
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
        # Make it plural (optional, adjust as needed)
        if name.endswith('y') and not name.endswith('ey'):
            name = name[:-1] + 'ies'
        elif not name.endswith('s'):
            name += 's'
        return name