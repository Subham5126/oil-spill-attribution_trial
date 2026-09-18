"""Add official_email and tech_admin provisioning fields.

Revision ID: 0003_official_email_tech_admin
Revises: 0002_add_auth_users
Create Date: 2026-09-18 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_official_email_tech_admin"
down_revision: Union[str, None] = "0002_add_auth_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("users")]

    with op.batch_alter_table("users") as batch_op:
        if "email" in columns and "official_email" not in columns:
            batch_op.alter_column("email", new_column_name="official_email", existing_type=sa.String(255))
        elif "official_email" not in columns:
            batch_op.add_column(sa.Column("official_email", sa.String(255), nullable=True))

        if "must_change_password" not in columns:
            batch_op.add_column(
                sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False)
            )

    # Ensure index exists on official_email
    indexes = [ix["name"] for ix in inspector.get_indexes("users")]
    if "ix_users_official_email" not in indexes:
        try:
            op.create_index("ix_users_official_email", "users", ["official_email"], unique=True)
        except Exception:
            pass


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("must_change_password")
        batch_op.alter_column("official_email", new_column_name="email", existing_type=sa.String(255))
