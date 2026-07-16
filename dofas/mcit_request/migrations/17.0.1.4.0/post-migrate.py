"""A previous version declared quotation_ref as required=True. Odoo's ORM
adds a NOT NULL constraint when a field becomes required, but never removes
one automatically when required is later dropped - that has to be done by
hand. Without this, the column stays NOT NULL forever and every attempt to
pre-create the wizard (before the user has typed a reference) keeps failing
with the same "mandatory field" error, no matter how the Python model reads.
This migration is idempotent and safe to run whether or not the constraint
is still present."""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mcit_spend_request_quotation_wizard'
          AND column_name = 'quotation_ref'
          AND is_nullable = 'NO'
    """)
    if cr.fetchone():
        cr.execute("""
            ALTER TABLE mcit_spend_request_quotation_wizard
            ALTER COLUMN quotation_ref DROP NOT NULL
        """)
