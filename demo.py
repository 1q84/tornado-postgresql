#!/usr/bin/env python
import database


db = database.Connection(host='127.0.0.1', database='postgres', user='postgres')
for item in db.query("SELECT * FROM person"):
    print item