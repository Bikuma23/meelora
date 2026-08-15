"""In-memory async Mongo fake for P1.13A access tests (no live side effects)."""
import uuid


def _get_path(doc, key):
    if "." not in key:
        return doc.get(key), (key in doc)
    cur = doc
    parts = key.split(".")
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None, False
    return cur, True


def _match(doc, query):
    for k, v in query.items():
        actual, present = _get_path(doc, k)
        if isinstance(v, dict):
            if "$ne" in v and actual == v["$ne"]:
                return False
            if "$in" in v and actual not in v["$in"]:
                return False
            if "$exists" in v and present != v["$exists"]:
                return False
        elif actual != v:
            return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *_a, **_k):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, _n=None):
        return [d.copy() for d in self._docs]


class _UpdateResult:
    def __init__(self, modified):
        self.modified_count = modified
        self.matched_count = modified


class _Col:
    def __init__(self):
        self.docs = []

    async def create_index(self, *_a, **_k):
        return "idx"

    async def insert_one(self, doc):
        d = dict(doc)
        d.setdefault("_id", f"id_{uuid.uuid4().hex}")
        self.docs.append(d)
        return type("R", (), {"inserted_id": d["_id"]})()

    async def insert_many(self, docs):
        for d in docs:
            await self.insert_one(d)

    async def find_one(self, query=None):
        query = query or {}
        for d in self.docs:
            if _match(d, query):
                return d.copy()
        return None

    def find(self, query=None):
        query = query or {}
        return _Cursor([d for d in self.docs if _match(d, query)])

    async def count_documents(self, query=None):
        query = query or {}
        return sum(1 for d in self.docs if _match(d, query))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                for k in update.get("$unset", {}):
                    d.pop(k, None)
                return _UpdateResult(1)
        if upsert:
            base = {k: v for k, v in query.items() if not isinstance(v, dict)}
            base.update(update.get("$setOnInsert", {}))
            base.update(update.get("$set", {}))
            await self.insert_one(base)
        return _UpdateResult(0)

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                self.docs.pop(i)
                return _UpdateResult(1)
        return _UpdateResult(0)


class FakeDB:
    def __init__(self):
        self._cols = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        cols = self.__dict__.setdefault("_cols", {})
        if name not in cols:
            cols[name] = _Col()
        return cols[name]
