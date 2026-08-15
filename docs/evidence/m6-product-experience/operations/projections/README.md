# Projection Rebuild and Recovery

Search, insights, and dashboard groups use registered generation-owned identifiers. Cold/warm
rebuild, validation, activation, retained-generation rollback, interruption cleanup, FTS integrity,
and idempotent startup checks pass. The search handler advanced to version 3 to force safe rebuilds
after removing technical snippet metadata. The three non-search product projection definitions use
handler version 2 and retain canonical, checksum-validated event envelopes in their generation-owned
source tables. Analytical readers resolve only registered allow-listed physical identifiers.
