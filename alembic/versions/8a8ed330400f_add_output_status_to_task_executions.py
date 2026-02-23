"""add_output_status_to_task_executions

Revision ID: 8a8ed330400f
Revises: 5369e283731d
Create Date: 2026-02-23 21:29:47.117867

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8a8ed330400f'
down_revision: Union[str, Sequence[str], None] = '5369e283731d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('task_executions', sa.Column('output_status', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('task_executions', 'output_status')
