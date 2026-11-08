# Admin user search returns 500 when the name contains an apostrophe

**Version:** 4.3.0 (the release that added the quick search on the admin Users page)
**Environment:** Ubuntu 24.04, Python 3.12, SQLite 3.45

**Steps to reproduce**
1. Sign in as an admin and open Admin > Users.
2. Type `O'Brien` in the search box and press Enter.

**Expected:** the users whose name contains O'Brien are listed.
**Actual:** HTTP 500. Every name containing an apostrophe fails the same way, and there is no other way to
look a user up by name, so support cannot find these accounts at all.

**Log**
```
sqlite3.OperationalError: near "Brien": syntax error
  File "api/users.py", line 17, in find_users
    return conn.execute(query).fetchall()
```
