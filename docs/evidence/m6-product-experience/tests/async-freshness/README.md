# Asynchronous Projection Freshness

Production projection jobs advance in global-position order and acknowledge only after every
active generation catches up. Search, care reports, analytics, and dashboard statistics consume
only the registered active generation; an integration test proves a newly appended event is not
visible before its checkpoint advances. Production web requests do not run projection work inline.
Startup generation checks are idempotent, and missing generations display safe catching-up states.
Rebuild, interruption, rollback, activation, cleanup, and FTS generation tests pass in
`test_product_projection_worker.py` and `test_projection_rebuilds.py`.
