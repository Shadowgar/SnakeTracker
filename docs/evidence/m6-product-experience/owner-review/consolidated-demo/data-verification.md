# Consolidated Data Verification

The following SHA-256 values cover canonical JSON encodings of every SQLite row in each real
household record set. They were captured immediately before rebuilding/provisioning and repeated
after the fictional household was populated. Every value remained identical.

| Protected record set | Rows | SHA-256 |
| --- | ---: | --- |
| Household summary | 1 | `b273a2e11359989ea307e8f1126b3a97a459e5aa5ff7e7982416d7ef7b7637b5` |
| Owner identity | 1 | `1cd5de49ed3bb035692b8e25e708d0c1571511eec469e10f45a9b7ef9e42d0bc` |
| Authorization membership | 1 | `2ff02e8124e9420550a6aacea9319902bf8628b3a8467d83654aa1b62173c66a` |
| Animal current state | 1 | `c65f3288501cb0c124defef87eb184c72f7971a6227a6b60d942733eadb69f44` |
| Immutable domain events | 15 | `fe44cd3a2298e072565e15a133cae07659e638fbd13f74ee108dfb936dfddd09` |
| Immutable attachment metadata | 1 | `86c8ecfea2fdb8c223382760ecb65104e21681aea6c04e426b0ac108b7d500ea` |

The existing attachment file checksum remained
`1b061498c023525ae3ced752a15b97d69f2433f80486aeab4ecd8cbc70820f38`.

The promoted post-provisioning database has two household summaries, two users, two active owner
memberships, 13 animals total, and passes `PRAGMA integrity_check`. The fictional household owns
exactly 12 animals, nine enclosures, 12 attachment versions, and 366 domain events.

Automated tests deny real-to-demo and demo-to-real list, direct URL/identifier, mutation,
attachment, search, and report access. Denied mutations do not advance the target stream. The real
owner record and password hash are unchanged; the normal login code path is the same path exercised
through the promoted HTTP runtime by the fictional owner.
