"""from_line_id was declared required=True in an earlier version. The ORM adds
a NOT NULL constraint when a field becomes required but never removes one
automatically when required is later dropped - that has to be done by hand,
or every attempt to create a transfer with only the destination line known
(the normal flow: the acquisition sets to_line_id, the user picks from_line_id
afterwards) keeps failing with the same "mandatory field" error. Idempotent
and safe to run whether or not the constraint is still present."""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mcit_budget_transfer'
          AND column_name = 'from_line_id'
          AND is_nullable = 'NO'
    """)
    if cr.fetchone():
        cr.execute("""
            ALTER TABLE mcit_budget_transfer
            ALTER COLUMN from_line_id DROP NOT NULL
        """)
