# Asynchronous Projection Freshness

Production projection jobs advance in global-position order and acknowledge only after every
active generation catches up. Startup generation checks are idempotent. Search displays a clear
catching-up state when no active generation is safely readable. Rebuild, interruption, rollback,
activation, cleanup, and FTS generation tests pass in `test_product_projection_worker.py` and
`test_projection_rebuilds.py`.
