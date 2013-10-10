#!/usr/bin/env python

import itertools
import logging
import time
import psycopg2
import types

class Connection(object):
    """A lightweight wrapper around psycopg2 DB-API connections.

    The main value we provide is wrapping rows in a dict/object so that
    columns can be accessed by name. Typical usage::

        db = database.Connection("localhost", "mydatabase")
        for article in db.query("SELECT * FROM articles"):
            print article.title

    Cursors are hidden by the implementation, but other than that, the methods
    are very similar to the DB-API.

    We explicitly set the timezone to UTC and the character encoding to
    UTF-8 on all connections to avoid time zone and encoding errors.
    """
    def __init__(self, host, database, user=None, password=None, port=None,
                 max_idle_time=7*3600):
        self.host = host
        self.database = database
        self.max_idle_time = max_idle_time

        args = "dbname=%s"%self.database
        if host is not None:
            args += " host=%s"%host
        if user is not None:
            args += " user=%s"% user
        if password is not None:
            args += " password=%s"% password
        if port is not None:
            args += " port=%s"% port

        self._db = None
        self._db_args = args
        self._last_use_time = time.time()
        try:
            self.reconnect()
        except Exception:
            logging.error("Cannot connect to PostgreSQL on %s", self.host,
                          exc_info=True)
            
    def __del__(self):
        self.close()

    def close(self):
        """Closes this database connection."""
        if getattr(self, "_db", None) is not None:
            self._db.close()
            self._db = None

    def reconnect(self):
        """Closes the existing database connection and re-opens it."""
        self.close()
        self._db = psycopg2.connect(self._db_args)
        # TODO: autocommit issue on version 2.0.X of psycopg2
        #self._db.autocommit = True

    def query(self, query, *parameters):
        """Returns a row list for the given query and parameters."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            column_names = [d[0] for d in cursor.description]
            return [Row(itertools.izip(column_names, row)) for row in cursor]
        finally:
            cursor.close()

    def get_limit(self, query, *parameters):
        """Returns the first row returned for the given query."""
        rows = self.query(query, *parameters)
        if not rows:
            return None
        elif len(rows) > 1:
            raise Exception("Multiple rows returned for Database.get() query")
        else:
            return rows[0]
        
    # rowcount is a more reasonable default return value than lastrowid,
    # but for historical compatibility execute() must return lastrowid.
    def execute(self, query, *parameters):
        """Executes the given query, returning the lastrowid from the query."""
        return self.execute_lastrowid(query, *parameters)

    def execute_and_fetch(self, query, *parameters):
        """Executes the given query, returning the current_id from the query."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            return cursor.fetchone()[0]
        finally:
            cursor.close()

    def execute_lastrowid(self, query, *parameters):
        """Executes the given query, returning the lastrowid from the query."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            return cursor.lastrowid
        finally:
            cursor.close()

    def execute_rowcount(self, query, *parameters):
        """Executes the given query, returning the rowcount from the query."""
        cursor = self._cursor()
        try:
            self._execute(cursor, query, parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    def executemany(self, query, parameters):
        """Executes the given query against all the given param sequences.

        We return the lastrowid from the query.
        """
        return self.executemany_lastrowid(query, parameters)

    def executemany_lastrowid(self, query, parameters):
        """Executes the given query against all the given param sequences.

        We return the lastrowid from the query.
        """
        cursor = self._cursor()
        try:
            cursor.executemany(query, parameters)
            self._db.commit()
            return cursor.lastrowid
        except OperationalError:
            logging.error("Error connecting to PostgreSQL on %s", self.host)
            self._db.rollback()
        finally:
            cursor.close()

    def executemany_rowcount(self, query, parameters):
        """Executes the given query against all the given param sequences.

        We return the rowcount from the query.
        """
        cursor = self._cursor()
        try:
            cursor.executemany(query, parameters)
            self._db.commit()
            return cursor.rowcount
        except OperationalError:
            logging.error("Error connecting to PostgreSQL on %s", self.host)
            self._db.rollback()
        finally:
            cursor.close()

    def _ensure_connected(self):
        # PostgreSQL by default closes client connections that are idle for
        # 8 hours, but the client library does not report this fact until
        # you try to perform a query and it fails.  Protect against this
        # case by preemptively closing and reopening the connection
        # if it has been idle for too long (7 hours by default).
        if (self._db is None or
            (time.time() - self._last_use_time > self.max_idle_time)):
            self.reconnect()
        self._last_use_time = time.time()

    def _cursor(self):
        self._ensure_connected()
        return self._db.cursor()

    def _execute(self, cursor, query, parameters):
        try:
            self._db.rollback()
            logging.info("DAOLog:ExecuteSql is %s"%cursor.mogrify(query, parameters))
            cursor.execute(query, parameters)
            self._db.commit()
        except OperationalError:
            logging.error("Error connecting to PostgreSQL on %s", self.host)
            self._db.rollback()
            cursor.execute(query, parameters)
            self._db.commit()
            
    def convert_point(self,param):
        if type(param) is types.NoneType:
            return 0
        try:
            return float(param)
        except ValueError:
            return 0

class Row(dict):
    """A dict that allows for object-like property access syntax."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)
        
OperationalError = psycopg2.OperationalError