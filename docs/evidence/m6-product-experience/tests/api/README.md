# M6 Read API

The authorized measurement endpoint is versioned, household-scoped, and returns ETags. A matching
`If-None-Match` produces `304`; unknown or cross-household animals fail without disclosure.
