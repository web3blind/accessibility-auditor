import Database from 'better-sqlite3';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
export class Ledger {
  constructor(path) {
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
    this.db = new Database(path);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('synchronous = FULL');
    this.db.pragma('busy_timeout = 5000');
    this.db.exec(`CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, status TEXT NOT NULL, tx TEXT, result TEXT);
      CREATE TABLE IF NOT EXISTS budget (day TEXT PRIMARY KEY, reserved TEXT NOT NULL);`);
  }
  claim(id) {
    return this.db.transaction(() => {
      if (this.db.prepare('SELECT 1 FROM attempts WHERE id=?').get(id)) throw new Error('authorization_replay');
      if (this.db.prepare("SELECT 1 FROM attempts WHERE status='pending'").get()) throw new Error('settlement_busy_or_recovery_required');
      this.db.prepare("INSERT INTO attempts(id,status) VALUES(?,'pending')").run(id);
    }).immediate();
  }
  reserve(cost, limit) {
    return this.db.transaction(() => {
      const day = new Date().toISOString().slice(0, 10);
      const old = BigInt(this.db.prepare('SELECT reserved FROM budget WHERE day=?').get(day)?.reserved || '0');
      if (old + cost > limit) throw new Error('daily_gas_budget_exceeded');
      this.db.prepare('INSERT INTO budget(day,reserved) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET reserved=excluded.reserved').run(day, String(old + cost));
    }).immediate();
  }
  tx(id, hash) { this.db.prepare('UPDATE attempts SET tx=? WHERE id=?').run(hash, id); }
  finish(id, result) { this.db.prepare("UPDATE attempts SET status='done',result=? WHERE id=?").run(JSON.stringify(result), id); }
  close() { this.db.close(); }
}
