from alembic import op
import sqlalchemy as sa

revision = "6bc875d7a4f8"
down_revision = "5ee1e9618646"


def upgrade() -> None:
    # 1) Add as NULLABLE first (because existing rows)
    op.add_column("group", sa.Column("major_id", sa.Uuid(), nullable=True))

    # 2) Create FK with an EXPLICIT NAME
    op.create_foreign_key(
        "fk_group_major_id_major",
        "group",
        "major",
        ["major_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 3) OPTIONAL (recommended): backfill existing rows here
    #    You MUST decide how to map group -> major. Examples:
    #    - if group_name prefix equals major.major_name
    #    - or you set a default major for old groups
    #
    # Example backfill by prefix matching major_name:
    op.execute("""
        UPDATE "group" g
        SET major_id = m.id
        FROM major m
        WHERE split_part(g.group_name, '-', 1) = m.major_name
          AND g.major_id IS NULL;
    """)

    # 4) If you truly want NOT NULL, only do it after backfill
    #    But ONLY if you're sure ALL groups now have major_id
    # op.alter_column("group", "major_id", nullable=False)


def downgrade() -> None:
    # Drop FK by NAME first, then column
    op.drop_constraint("fk_group_major_id_major", "group", type_="foreignkey")
    op.drop_column("group", "major_id")
