#!/usr/bin/env node
// 一次性：把 /root/.dsh/sessions 下的 .v3.jsonl.zstd 全部索引进 session-search.db
// 用 dsh 兼容的 FTS5 schema（persisted_sessions + persisted_docs）
// 文本抽取：递归从事件 data 提取可读字段；header 也建一条 doc（cwd 等能搜到）
// node:sqlite (node 22 内建)
import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { readdir, stat, mkdir } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { join } from 'node:path';
import zlib from 'node:zlib';
import { readdirSync } from 'node:fs';

const HOME = '/root/.dsh';
const DB = join(HOME, 'session-search.db');
const SESS_ROOT = join(HOME, 'sessions');

function ensureSchema(db) {
	db.exec(`CREATE TABLE IF NOT EXISTS search_state (singleton INTEGER PRIMARY KEY CHECK (singleton=1), global_generation INTEGER NOT NULL) STRICT`);
	db.exec(`INSERT OR IGNORE INTO search_state (singleton,global_generation) VALUES (1,0)`);
	db.exec(`CREATE TABLE IF NOT EXISTS persisted_sessions (id TEXT PRIMARY KEY, version INTEGER NOT NULL, created_at INTEGER NOT NULL, cwd TEXT, parent_session TEXT, seed_length INTEGER, delegation_depth INTEGER, agent_preset TEXT, revision TEXT NOT NULL, generation INTEGER NOT NULL) STRICT`);
	db.exec(`CREATE VIRTUAL TABLE IF NOT EXISTS persisted_docs USING fts5(text, session_id UNINDEXED, seq UNINDEXED, type UNINDEXED, time UNINDEXED, surface UNINDEXED, codepoint_length UNINDEXED, tokenize='unicode61')`);
}

function readZstdAll(path) {
	return import('node:fs').then(({ readFileSync }) => {
		const buf = readFileSync(path);
		const offs = [];
		for (let i = 0; i <= buf.length - 4; i++) {
			if (buf[i] === 0x28 && buf[i+1] === 0xB5 && buf[i+2] === 0x2F && buf[i+3] === 0xFD) offs.push(i);
			else if (buf[i] >= 0x50 && buf[i] <= 0x5F && buf[i+1] === 0x2A && buf[i+2] === 0x4D && buf[i+3] === 0x18) offs.push(i);
		}
		const parts = [];
		for (let k = 0; k < offs.length; k++) {
			const start = offs[k], end = (k + 1 < offs.length) ? offs[k+1] : buf.length;
			try { parts.push(zlib.zstdDecompressSync(buf.subarray(start, end))); } catch {}
		}
		return Buffer.concat(parts);
	});
}
const rev = h => createHash('sha256').update(JSON.stringify(h)).digest('hex');

// 递归从对象里抽所有字符串字段，拼成可索引文本（限长避免过大）
function extractText(o, max = 4000) {
	const out = [];
	function walk(v) {
		if (out.length >= max) return;
		if (typeof v === 'string') { if (v.trim()) out.push(v); }
		else if (Array.isArray(v)) { for (const x of v) walk(x); if (out.length >= max) return; }
		else if (v && typeof v === 'object') { for (const k of Object.keys(v)) walk(v[k]); }
	}
	walk(o);
	return out.join('\n').slice(0, max);
}

function buildDocs(header, events) {
	const docs = [];
	// header doc（cwd/preset 等能搜到；ai_comic 工作流靠 cwd 命中）
	const ht = ['cwd:' + (header.cwd ?? ''), 'preset:' + (header.agentPreset ?? ''), 'id:' + header.id, 'v' + (header.version ?? '')].join('\n');
	docs.push({ text: ht, sessionId: header.id, seq: -1, type: 'header', time: header.createdAt ?? 0, surface: 'header' });
	// 事件 docs
	for (const ev of events) {
		const t = extractText(ev.data ?? {});
		if (t) docs.push({ text: t, sessionId: header.id, seq: ev.seq ?? 0, type: String(ev.type ?? ''), time: ev.time ?? 0, surface: String(ev.type ?? '') });
	}
	return docs;
}

async function main() {
	await mkdir(HOME, { recursive: true });
	const db = new DatabaseSync(DB);
	ensureSchema(db);
	console.log('db:', DB);

	// scan all cwd buckets: sessions/<bucket>/session-*/session.v3.jsonl.zstd
	const buckets = (await readdir(SESS_ROOT, { withFileTypes: true })).filter(d => d.isDirectory());
	const dirs = [];
	for (const b of buckets) {
		for (const sd of await readdir(join(SESS_ROOT, b.name), { withFileTypes: true })) {
			if (sd.isDirectory() && sd.name.startsWith('session-')) dirs.push(join(b.name, sd.name));
		}
	}
	console.log('发现 session:', dirs.length);

	// phase1: 异步读+解析所有 session
	const records = [];
	for (const rel of dirs) {
		const zpath = join(SESS_ROOT, rel, 'session.v3.jsonl.zstd');
		try { await stat(zpath); } catch { continue; }
		let buf;
		try { buf = await readZstdAll(zpath); } catch (e) { console.log('  zstd fail', rel, e.message); continue; }
		const lines = buf.toString('utf8').split('\n').filter(Boolean);
		if (lines.length < 1) continue;
		let header; try { header = JSON.parse(lines[0]); } catch { continue; }
		if (!header.id) continue;
		const events = [];
		for (let i = 1; i < lines.length; i++) {
			try {
				const o = JSON.parse(lines[i]);
				// 只保留真正的事件行（有 seq 编号 + type）
				if (typeof o.seq === 'number' && typeof o.type === 'string') events.push(o);
			} catch {}
		}
		records.push({ header, events });
	}
	console.log('成功解析:', records.length);

	// phase2: 同步事务入库
	db.exec('BEGIN');
	try {
		const delS = db.prepare(`DELETE FROM persisted_sessions WHERE id=?`);
		const delD = db.prepare(`DELETE FROM persisted_docs WHERE session_id=?`);
		const insS = db.prepare(`INSERT INTO persisted_sessions (id,version,created_at,cwd,parent_session,seed_length,delegation_depth,agent_preset,revision,generation) VALUES (?,?,?,?,?,?,?,?,?,?)`);
		const insD = db.prepare(`INSERT INTO persisted_docs (text,session_id,seq,type,time,surface,codepoint_length) VALUES (?,?,?,?,?,?,?)`);
		let totalDocs = 0;
		for (const { header, events } of records) {
			const inh = header.inheritedEventCount ?? 0;
			delS.run(header.id); delD.run(header.id);
			insS.run(header.id, header.version ?? 3, header.createdAt, header.cwd ?? null,
				header.parentSession ?? null, header.isSeeded ? inh : null,
				header.delegationDepth ?? null, header.agentPreset ?? null, rev(header), 0);
			const docs = buildDocs(header, events);
			for (const doc of docs) {
				insD.run(doc.text, doc.sessionId, doc.seq, doc.type, doc.time, doc.surface, Array.from(doc.text).length);
			}
			totalDocs += docs.length;
			console.log(`  ${header.id.slice(0,8)}… events=${events.length} fts=${docs.length}`);
		}
		db.exec(`UPDATE search_state SET global_generation=1 WHERE singleton=1`);
		db.exec('COMMIT');
		console.log('docs 总数:', totalDocs);
	} catch (e) {
		db.exec('ROLLBACK'); throw e;
	}
	db.close();
	console.log('完成。');
}
main().catch(e => { console.error(e); process.exit(1); });
