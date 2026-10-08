import json, sqlite3, threading, os
from pathlib import Path

class MemoryStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('GTA_MEMORY_DB','workspace/agent_memory.sqlite3'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.lock, sqlite3.connect(self.path) as c:
            c.execute('''CREATE TABLE IF NOT EXISTS experiments(id INTEGER PRIMARY KEY, created_at TEXT, problem TEXT, strategy TEXT, result TEXT, score_before REAL, score_after REAL, success INTEGER, details TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY, value TEXT)''')

    def record(self, problem, strategy, result, score_before=0, score_after=0, success=False, details=None):
        with self.lock, sqlite3.connect(self.path) as c:
            c.execute('INSERT INTO experiments(created_at,problem,strategy,result,score_before,score_after,success,details) VALUES(datetime("now"),?,?,?,?,?,?,?)',
                      (problem,strategy,result,float(score_before),float(score_after),int(bool(success)),json.dumps(details or {},ensure_ascii=False)))

    def best(self, problem):
        with self.lock, sqlite3.connect(self.path) as c:
            rows=c.execute('SELECT strategy,AVG(score_after-score_before) gain,SUM(success) wins,COUNT(*) n FROM experiments WHERE problem=? GROUP BY strategy ORDER BY wins DESC,gain DESC,n DESC',(problem,)).fetchall()
        return [{'strategy':r[0],'gain':r[1],'wins':r[2],'n':r[3]} for r in rows]

    def recent(self, limit=30):
        with self.lock, sqlite3.connect(self.path) as c:
            rows=c.execute('SELECT created_at,problem,strategy,result,score_before,score_after,success,details FROM experiments ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(zip(['created_at','problem','strategy','result','score_before','score_after','success','details'],r)) for r in rows]
