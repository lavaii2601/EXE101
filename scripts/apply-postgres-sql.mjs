import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import pg from 'pg';

const { Pool } = pg;
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');
const relativeSqlPath = process.argv[2];

if (!relativeSqlPath) {
  console.error('Usage: node scripts/apply-postgres-sql.mjs <path-to-sql>');
  process.exit(1);
}

if (!process.env.DATABASE_URL) {
  console.error('Error: DATABASE_URL is not set.');
  process.exit(1);
}

const sqlPath = path.resolve(projectRoot, relativeSqlPath);
if (!fs.existsSync(sqlPath)) {
  console.error(`Error: SQL file not found: ${sqlPath}`);
  process.exit(1);
}

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

async function applySql() {
  try {
    const sql = fs.readFileSync(sqlPath, 'utf8');
    await pool.query(sql);
    console.log(`Applied SQL successfully: ${relativeSqlPath}`);
  } catch (error) {
    console.error('Error applying SQL:', error.message);
    process.exitCode = 1;
  } finally {
    await pool.end();
  }
}

applySql();
