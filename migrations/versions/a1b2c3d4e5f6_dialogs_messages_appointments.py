"""dialogs messages appointments

Revision ID: a1b2c3d4e5f6
Revises: cc3aa45b60fd
Create Date: 2025-03-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "cc3aa45b60fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dialogs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="telegram"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(datetime('now'))"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(datetime('now'))"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dialogs_user_id"), "dialogs", ["user_id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dialog_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(length=16), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(datetime('now'))"), nullable=False),
        sa.ForeignKeyConstraint(["dialog_id"], ["dialogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_dialog_id"), "messages", ["dialog_id"], unique=False)

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("dialog_id", sa.Integer(), nullable=True),
        sa.Column("client_name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("service", sa.String(), nullable=False),
        sa.Column("doctor", sa.String(), nullable=True),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="telegram"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'created'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(datetime('now'))"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(datetime('now'))"), nullable=False),
        sa.ForeignKeyConstraint(["dialog_id"], ["dialogs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_appointments_user_id"), "appointments", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_appointments_user_id"), table_name="appointments")
    op.drop_table("appointments")
    op.drop_index(op.f("ix_messages_dialog_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_dialogs_user_id"), table_name="dialogs")
    op.drop_table("dialogs")
