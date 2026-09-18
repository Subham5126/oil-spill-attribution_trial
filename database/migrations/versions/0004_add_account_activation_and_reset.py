"""Add account activation and password reset fields.

Revision ID: 0004_account_activation_reset
Revises: 0003_official_email_tech_admin
Create Date: 2026-09-18 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_account_activation_reset"
down_revision: Union[str, None] = "0003_official_email_tech_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("users")]

    with op.batch_alter_table("users") as batch_op:
        if "account_status" not in columns:
            batch_op.add_column(
                sa.Column("account_status", sa.String(32), server_default="ACTIVE", nullable=False)
            )
        if "activation_token_hash" not in columns:
            batch_op.add_column(
                sa.Column("activation_token_hash", sa.String(64), nullable=True)
            )
        if "activation_token_expires_at" not in columns:
            batch_op.add_column(
                sa.Column("activation_token_expires_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "activation_used_at" not in columns:
            batch_op.add_column(
                sa.Column("activation_used_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "reset_token_hash" not in columns:
            batch_op.add_column(
                sa.Column("reset_token_hash", sa.String(64), nullable=True)
            )
        if "reset_token_expires_at" not in columns:
            batch_op.add_column(
                sa.Column("reset_token_expires_at", sa.DateTime(timezone=True), nullable=True)
            )
        if "last_invitation_sent_at" not in columns:
            batch_op.add_column(
                sa.Column("last_invitation_sent_at", sa.DateTime(timezone=True), nullable=True)
            )
        # Make password_hash nullable so pending accounts don't require placeholder hashes
        batch_op.alter_column("password_hash", nullable=True, existing_type=sa.String(255))

    indexes = [ix["name"] for ix in inspector.get_indexes("users")]
    if "ix_users_activation_token_hash" not in indexes:
        try:
            op.create_index("ix_users_activation_token_hash", "users", ["activation_token_hash"])
        except Exception:
            pass
    if "ix_users_reset_token_hash" not in indexes:
        try:
            op.create_index("ix_users_reset_token_hash", "users", ["reset_token_hash"])
        except Exception:
            pass


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("last_invitation_sent_at")
        batch_op.drop_column("reset_token_expires_at")
        batch_op.drop_column("reset_token_hash")
        batch_op.drop_column("activation_used_at")
        batch_op.drop_column("activation_token_expires_at")
        batch_op.drop_column("activation_token_hash")
        batch_op.drop_column("account_status")
        batch_op.alter_column("password_hash", nullable=False, existing_type=sa.String(255))
