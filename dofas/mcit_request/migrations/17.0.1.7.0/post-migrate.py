"""This version adds mcit.commitment.spend_request_id, a real Many2one used by
the new commitment_ids One2many on mcit.spend.request (needed so a single
acquisition can hold several reserves when its approved amount is split
across budget lines). The ORM creates the new, empty column, but every
commitment created by an *older* version of this module only recorded its
link back to the acquisition in the generic `source_ref` Reference field
(e.g. 'mcit.spend.request,42') - it never populated a column that didn't
exist yet. Without this backfill, every acquisition committed before this
upgrade would suddenly show an empty 'Budget Reserves' tab and print a
voucher that fell back to the pre-split single-line summary, even though its
commitment is right there. Idempotent and safe to run more than once."""


def migrate(cr, version):
    cr.execute("""
        UPDATE mcit_commitment
        SET spend_request_id = split_part(source_ref, ',', 2)::integer
        WHERE spend_request_id IS NULL
          AND source_ref LIKE 'mcit.spend.request,%'
          AND split_part(source_ref, ',', 2) ~ '^[0-9]+$'
    """)
